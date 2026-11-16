from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.wire.message import pack_unsigned, unpack_unsigned

OPERATION_STATUS = 16
OPERATION_ENDPOINT = 17
OPERATION_ACCESS = 18
OPERATION_LAUNCH = 19
OPERATION_APPLICATIONS = 20
OPERATION_SIGNAL = 21
OPERATION_WAIT = 22
OPERATION_MEMORY = 23
OPERATION_POWER = 24
SYSTEM_STARTING = 0
SYSTEM_RUNNING = 1
SYSTEM_DEGRADED = 2
SYSTEM_STOPPING = 3
SYSTEM_STATE_NAMES = ("starting", "running", "degraded", "stopping")
SERVICE_STOPPED = 0
SERVICE_STARTING = 1
SERVICE_READY = 2
SERVICE_DEGRADED = 3
SERVICE_BLOCKED = 4
SERVICE_STATE_NAMES = ("stopped", "starting", "ready", "degraded", "blocked")
APPLICATION_RUNNING = 1
APPLICATION_EXITED = 2
APPLICATION_STATE_NAMES = ("unknown", "running", "exited")
MAX_COMMAND_BYTES = 63
MAX_NAME_BYTES = 32
WAIT_FOREVER = 0xFFFFFFFFFFFFFFFF
NO_WAIT = 0
COUNTER_BYTES = 8
SERVICE_FIXED_BYTES = 5
APPLICATION_FIXED_BYTES = 12
WAIT_BYTES = 12
OUTCOME_BYTES = 5


class ServiceStatus:
    def __init__(self, name: str, state: int, failures: int, restarts: int, starts: int) -> None:
        self.name = name
        self.state = state
        self.failures = failures
        self.restarts = restarts
        self.starts = starts


class ApplicationStatus:
    def __init__(self, identity: int, state: int, reason: int, value: int, command: str) -> None:
        self.identity = identity
        self.state = state
        self.reason = reason
        self.value = value
        self.command = command


def malformed() -> KernelError:
    return KernelError(
        INVALID_ARGUMENT, "control request does not have the layout of its operation"
    )


def exactly(payload: bytes, size: int) -> bytes:
    if len(payload) != size:
        raise malformed()
    return payload


def encode_name(name: str) -> bytes:
    encoded = bytes(name, "utf-8")
    if not encoded or len(encoded) > MAX_NAME_BYTES:
        raise malformed()
    return encoded


def decode_name(body: bytes) -> str:
    if not body or len(body) > MAX_NAME_BYTES:
        raise malformed()
    return str(body, "utf-8")


def encode_status(state: int, services: list[ServiceStatus]) -> bytes:
    parts = [pack_unsigned(state, 1), pack_unsigned(len(services), 1)]
    for service in services:
        name = bytes(service.name, "utf-8")
        parts.append(
            pack_unsigned(service.state, 1)
            + pack_unsigned(service.failures, 1)
            + pack_unsigned(service.restarts, 1)
            + pack_unsigned(service.starts, 1)
            + pack_unsigned(len(name), 1)
            + name
        )
    return b"".join(parts)


def decode_status(payload: bytes) -> tuple[int, list[ServiceStatus]]:
    if len(payload) < 2:
        raise malformed()
    services = []
    position = 2
    for _ in range(payload[1]):
        if len(payload) < position + SERVICE_FIXED_BYTES:
            raise malformed()
        end = position + SERVICE_FIXED_BYTES + payload[position + 4]
        if len(payload) < end:
            raise malformed()
        services.append(
            ServiceStatus(
                str(payload[position + SERVICE_FIXED_BYTES : end], "utf-8"),
                payload[position],
                payload[position + 1],
                payload[position + 2],
                payload[position + 3],
            )
        )
        position = end
    if position != len(payload):
        raise malformed()
    return payload[0], services


def encode_identity(identity: int) -> bytes:
    return pack_unsigned(identity, 4)


def decode_identity(body: bytes) -> int:
    return unpack_unsigned(exactly(body, 4), 0, 4)


def encode_applications(applications: list[ApplicationStatus]) -> bytes:
    parts = []
    for application in applications:
        command = bytes(application.command, "utf-8")
        parts.append(
            pack_unsigned(application.identity, 4)
            + pack_unsigned(application.state, 1)
            + pack_unsigned(application.reason, 1)
            + pack_unsigned(application.value, 4)
            + pack_unsigned(len(command), 2)
            + command
        )
    return b"".join(parts)


def decode_applications(payload: bytes) -> list[ApplicationStatus]:
    applications = []
    position = 0
    while position < len(payload):
        if len(payload) < position + APPLICATION_FIXED_BYTES:
            raise malformed()
        end = (
            position
            + APPLICATION_FIXED_BYTES
            + unpack_unsigned(payload, position + 10, position + 12)
        )
        if len(payload) < end:
            raise malformed()
        applications.append(
            ApplicationStatus(
                unpack_unsigned(payload, position, position + 4),
                payload[position + 4],
                payload[position + 5],
                unpack_unsigned(payload, position + 6, position + 10),
                str(payload[position + APPLICATION_FIXED_BYTES : end], "utf-8"),
            )
        )
        position = end
    return applications


def encode_wait(identity: int, timeout_nanoseconds: int) -> bytes:
    return pack_unsigned(identity, 4) + pack_unsigned(timeout_nanoseconds, 8)


def decode_wait(body: bytes) -> tuple[int, int]:
    exactly(body, WAIT_BYTES)
    return unpack_unsigned(body, 0, 4), unpack_unsigned(body, 4, 12)


def encode_outcome(reason: int, value: int) -> bytes:
    return pack_unsigned(reason, 1) + pack_unsigned(value, 4)


def decode_outcome(payload: bytes) -> tuple[int, int]:
    exactly(payload, OUTCOME_BYTES)
    return payload[0], unpack_unsigned(payload, 1, 5)


def encode_counters(counters: tuple[int, ...]) -> bytes:
    return b"".join([pack_unsigned(value, COUNTER_BYTES) for value in counters])


def decode_counters(payload: bytes) -> list[int]:
    if len(payload) % COUNTER_BYTES:
        raise malformed()
    return [
        unpack_unsigned(payload, start, start + COUNTER_BYTES)
        for start in range(0, len(payload), COUNTER_BYTES)
    ]


def encode_action(action: int) -> bytes:
    return pack_unsigned(action, 1)


def decode_action(body: bytes) -> int:
    return exactly(body, 1)[0]
