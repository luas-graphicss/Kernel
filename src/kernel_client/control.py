from kernel_client import services
from kernel_protocol.services.control import (
    OPERATION_ACCESS,
    OPERATION_APPLICATIONS,
    OPERATION_ENDPOINT,
    OPERATION_LAUNCH,
    OPERATION_MEMORY,
    OPERATION_POWER,
    OPERATION_SIGNAL,
    OPERATION_STATUS,
    OPERATION_WAIT,
    WAIT_FOREVER,
    ApplicationStatus,
    ServiceStatus,
    decode_applications,
    decode_counters,
    decode_identity,
    decode_outcome,
    decode_status,
    encode_action,
    encode_identity,
    encode_name,
    encode_wait,
)


class Control:
    def __init__(self, endpoint: int) -> None:
        self._endpoint = endpoint

    def status(self) -> tuple[int, list[ServiceStatus]]:
        return decode_status(self._call(OPERATION_STATUS))

    def endpoint_of(self, service: str) -> int:
        _payload, capability = services.call(
            self._endpoint, OPERATION_ENDPOINT, encode_name(service)
        )
        return capability

    def access_to(self, service: str) -> int:
        _payload, capability = services.call(self._endpoint, OPERATION_ACCESS, encode_name(service))
        return capability

    def launch(self, command: bytes) -> int:
        return decode_identity(self._call(OPERATION_LAUNCH, command))

    def applications(self) -> list[ApplicationStatus]:
        return decode_applications(self._call(OPERATION_APPLICATIONS))

    def signal(self, application: int) -> None:
        self._call(OPERATION_SIGNAL, encode_identity(application))

    def wait(self, application: int, timeout_nanoseconds: int = WAIT_FOREVER) -> tuple[int, int]:
        return decode_outcome(
            self._call(OPERATION_WAIT, encode_wait(application, timeout_nanoseconds))
        )

    def memory(self) -> list[int]:
        return decode_counters(self._call(OPERATION_MEMORY))

    def power(self, action: int) -> None:
        self._call(OPERATION_POWER, encode_action(action))

    def _call(self, operation: int, body: bytes = b"") -> bytes:
        payload, _received = services.call(self._endpoint, operation, body)
        return payload
