from kernel_protocol.configuration.model import Applications as Policy
from kernel_protocol.errors.codes import (
    BAD_STATE,
    INVALID_ARGUMENT,
    LIMIT_EXCEEDED,
    NOT_FOUND,
    KernelError,
)
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import REASON_NAMES
from kernel_protocol.services.control import (
    APPLICATION_EXITED,
    APPLICATION_RUNNING,
    ApplicationStatus,
)
from kernel_protocol.services.launch import (
    HAS_FILES,
    HAS_NETWORK,
    MAX_COMMAND_BYTES,
    encode_launch,
)
from kernel_services.manager import processes
from kernel_services.manager.journal import report
from kernel_services.manager.processes import Launcher, Program, Started
from kernel_services.manager.resources import Resources

RUNNER_PROGRAM = "kernel_apps.runner.main"
LAUNCH_TIMEOUT_NANOSECONDS = 10000000000
HISTORY = 8
FIRST_PRINTABLE = 0x21
LAST_PRINTABLE = 0x7E
SPACE = 0x20
NO_REASON = 0
NOT_CONFIGURED = "applications are not admitted"
UNKNOWN = "no application has this identity"


class Application:
    def __init__(self, identity: int, command: str, started: Started) -> None:
        self.identity = identity
        self.command = command
        self.started = started
        self.state = APPLICATION_RUNNING
        self.reason = NO_REASON
        self.value = 0


def checked_command(command: bytes) -> str:
    if not command or len(command) > MAX_COMMAND_BYTES or command[0] == SPACE:
        raise KernelError(INVALID_ARGUMENT, "a command names a program within the launch limit")
    for value in command:
        if value != SPACE and (value < FIRST_PRINTABLE or value > LAST_PRINTABLE):
            raise KernelError(INVALID_ARGUMENT, "a command holds printable characters only")
    return str(command, "utf-8")


class Applications:
    def __init__(self, launcher: Launcher, resources: Resources) -> None:
        self._launcher = launcher
        self._resources = resources
        self._policy: Policy | None = None
        self._known: list[Application] = []
        self._last = 0
        self.is_admitting = True

    def configure(self, policy: Policy) -> None:
        self._policy = policy

    def launch(self, command: bytes) -> int:
        policy = self._policy
        if policy is None or not self.is_admitting:
            raise KernelError(BAD_STATE, NOT_CONFIGURED)
        if self.running() >= policy.limit:
            raise KernelError(LIMIT_EXCEEDED, "the limit of running applications was reached")
        text = checked_command(command)
        resources = 0
        grants = []
        if self._resources.has_files(policy.access):
            resources |= HAS_FILES
            grants.append((self._resources.endpoint_of("storage", policy.access), RIGHT_SEND))
            grants.append((self._resources.access_to("storage", policy.access), RIGHT_SEND))
        if self._resources.has_network(policy.access):
            resources |= HAS_NETWORK
            grants.append((self._resources.endpoint_of("network", policy.access), RIGHT_SEND))
            grants.append((self._resources.access_to("network", policy.access), RIGHT_SEND))
        program = Program(RUNNER_PROGRAM, policy.priority, policy.heap_bytes, False)
        started = self._launcher.launch(
            program, tuple(grants), encode_launch(resources, command), LAUNCH_TIMEOUT_NANOSECONDS
        )
        self._last += 1
        self._known.append(Application(self._last, text, started))
        self._forget_oldest()
        report(f"application={self._last} state=running program={text.split(' ')[0]}")
        return self._last

    def running(self) -> int:
        return len([known for known in self._known if known.state == APPLICATION_RUNNING])

    def reap(self) -> None:
        for application in self._known:
            if application.state != APPLICATION_RUNNING:
                continue
            if processes.has_exited(application.started.process):
                self._finish(application)

    def signal(self, identity: int) -> None:
        application = self._find(identity)
        if application.state != APPLICATION_RUNNING:
            raise KernelError(BAD_STATE, "the application already exited")
        processes.terminate(application.started.process)
        self._finish(application)

    def outcome(self, identity: int) -> tuple[int, int] | None:
        application = self._find(identity)
        if application.state == APPLICATION_RUNNING:
            return None
        return application.reason, application.value

    def stop_all(self) -> int:
        stopped = 0
        self.is_admitting = False
        for application in self._known:
            if application.state == APPLICATION_RUNNING:
                processes.terminate(application.started.process)
                self._finish(application)
                stopped += 1
        return stopped

    def statuses(self) -> list[ApplicationStatus]:
        return [
            ApplicationStatus(known.identity, known.state, known.reason, known.value, known.command)
            for known in self._known
        ]

    def _find(self, identity: int) -> Application:
        for application in self._known:
            if application.identity == identity:
                return application
        raise KernelError(NOT_FOUND, UNKNOWN)

    def _finish(self, application: Application) -> None:
        client = application.started.identity
        application.reason, application.value = processes.collect(application.started)
        application.state = APPLICATION_EXITED
        self._resources.evict(client)
        report(
            f"application={application.identity} state=exited "
            f"reason={REASON_NAMES[application.reason]} value={application.value}"
        )

    def _forget_oldest(self) -> None:
        exited = [known for known in self._known if known.state == APPLICATION_EXITED]
        while len(exited) > HISTORY:
            self._known.remove(exited.pop(0))
