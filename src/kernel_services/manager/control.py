from kernel_client import capabilities, ipc, services, system
from kernel_client.services import Reply
from kernel_protocol.configuration.model import (
    CONTROL_LAUNCH,
    CONTROL_OBSERVE,
    CONTROL_POWER,
    CONTROL_SIGNAL,
)
from kernel_protocol.errors.codes import (
    BAD_STATE,
    CANCELLED,
    INVALID_ARGUMENT,
    LIMIT_EXCEEDED,
    TIMED_OUT,
    UNSUPPORTED,
    KernelError,
)
from kernel_protocol.identity.rights import RIGHT_DELEGATE, RIGHT_SEND
from kernel_protocol.services.control import (
    NO_WAIT,
    OPERATION_ACCESS,
    OPERATION_APPLICATIONS,
    OPERATION_ENDPOINT,
    OPERATION_LAUNCH,
    OPERATION_MEMORY,
    OPERATION_POWER,
    OPERATION_SIGNAL,
    OPERATION_STATUS,
    OPERATION_WAIT,
    SYSTEM_STOPPING,
    WAIT_FOREVER,
    decode_action,
    decode_identity,
    decode_name,
    decode_wait,
    encode_applications,
    encode_counters,
    encode_identity,
    encode_outcome,
    encode_status,
)
from kernel_protocol.system.power import POWER_ACTION_RESTART, POWER_ACTION_SHUTDOWN
from kernel_services.manager.applications import Applications
from kernel_services.manager.clients import Clients
from kernel_services.manager.resources import Resources
from kernel_services.manager.supervision import Supervisor

MAX_WAITS = 8
NEVER = 1 << 62
NO_REQUEST = -1
SHARED_RIGHTS = RIGHT_SEND | RIGHT_DELEGATE


class Wait:
    def __init__(self, request: ipc.Received, application: int, deadline: int) -> None:
        self.request = request
        self.application = application
        self.deadline = deadline


class ControlService:
    def __init__(
        self,
        system_handle: int,
        supervisor: Supervisor,
        applications: Applications,
        resources: Resources,
        clients: Clients,
    ) -> None:
        self._system = system_handle
        self._supervisor = supervisor
        self._applications = applications
        self._resources = resources
        self._clients = clients
        self._waits: list[Wait] = []
        self._now = 0
        self.is_stopping = False
        self.requested_action = NO_REQUEST
        self._handlers = {
            OPERATION_STATUS: self._status,
            OPERATION_ENDPOINT: self._endpoint,
            OPERATION_ACCESS: self._access,
            OPERATION_LAUNCH: self._launch,
            OPERATION_APPLICATIONS: self._list_applications,
            OPERATION_SIGNAL: self._signal,
            OPERATION_WAIT: self._wait,
            OPERATION_MEMORY: self._memory,
            OPERATION_POWER: self._power,
        }

    def arrive(self, request: ipc.Received, now: int) -> None:
        self._now = now
        if request.reply == 0:
            services.discard_transfer(request)
            return
        if request.transferred != ipc.NO_TRANSFER:
            services.discard_transfer(request)
            services.refuse(request, INVALID_ARGUMENT)
            return
        handler = self._handlers.get(request.message.operation)
        try:
            if handler is None:
                raise KernelError(UNSUPPORTED, "operation is not part of the control service")
            reply = handler(request)
        except KernelError as error:
            services.refuse(request, error.code)
            return
        if reply is not None:
            services.respond(request, reply)

    def settle(self, now: int) -> None:
        for wait in list(self._waits):
            outcome = self._outcome_or_gone(wait.application)
            if outcome is not None:
                self._waits.remove(wait)
                services.respond(wait.request, Reply(encode_outcome(outcome[0], outcome[1])))
            elif wait.deadline <= now:
                self._waits.remove(wait)
                services.refuse(wait.request, TIMED_OUT)

    def cancel_waits(self) -> None:
        for wait in self._waits:
            services.refuse(wait.request, CANCELLED)
        self._waits = []

    def _outcome_or_gone(self, application: int) -> tuple[int, int] | None:
        try:
            return self._applications.outcome(application)
        except KernelError:
            return 0, 0

    def _status(self, request: ipc.Received) -> Reply:
        self._clients.require(request.sender, CONTROL_OBSERVE)
        state = SYSTEM_STOPPING if self.is_stopping else self._supervisor.state()
        return Reply(encode_status(state, self._supervisor.statuses()))

    def _endpoint(self, request: ipc.Received) -> None:
        access = self._clients.access_of(request.sender)
        service = decode_name(request.message.payload)
        shared = capabilities.derive(self._resources.endpoint_of(service, access), SHARED_RIGHTS)
        services.respond(request, Reply(b"", shared))
        capabilities.close(shared)

    def _access(self, request: ipc.Received) -> Reply:
        access = self._clients.access_of(request.sender)
        service = decode_name(request.message.payload)
        return Reply(b"", self._resources.access_to(service, access))

    def _launch(self, request: ipc.Received) -> Reply:
        self._clients.require(request.sender, CONTROL_LAUNCH)
        if self.is_stopping:
            raise KernelError(BAD_STATE, "the system is stopping")
        return Reply(encode_identity(self._applications.launch(request.message.payload)))

    def _list_applications(self, request: ipc.Received) -> Reply:
        self._clients.require(request.sender, CONTROL_OBSERVE)
        return Reply(encode_applications(self._applications.statuses()))

    def _signal(self, request: ipc.Received) -> Reply:
        self._clients.require(request.sender, CONTROL_SIGNAL)
        self._applications.signal(decode_identity(request.message.payload))
        return Reply()

    def _wait(self, request: ipc.Received) -> Reply | None:
        self._clients.require(request.sender, CONTROL_OBSERVE)
        application, timeout = decode_wait(request.message.payload)
        outcome = self._applications.outcome(application)
        if outcome is not None:
            return Reply(encode_outcome(outcome[0], outcome[1]))
        if timeout == NO_WAIT:
            raise KernelError(TIMED_OUT, "the application is still running")
        if len(self._waits) == MAX_WAITS:
            raise KernelError(LIMIT_EXCEEDED, "too many waits are pending")
        deadline = NEVER if timeout == WAIT_FOREVER else self._now + timeout
        self._waits.append(Wait(request, application, deadline))
        return None

    def _memory(self, request: ipc.Received) -> Reply:
        self._clients.require(request.sender, CONTROL_OBSERVE)
        return Reply(encode_counters(system.counters(self._system)))

    def _power(self, request: ipc.Received) -> Reply:
        self._clients.require(request.sender, CONTROL_POWER)
        action = decode_action(request.message.payload)
        if action != POWER_ACTION_SHUTDOWN and action != POWER_ACTION_RESTART:
            raise KernelError(INVALID_ARGUMENT, "unknown power action")
        if self.is_stopping:
            raise KernelError(BAD_STATE, "the system is already stopping")
        self.is_stopping = True
        self.requested_action = action
        return Reply()
