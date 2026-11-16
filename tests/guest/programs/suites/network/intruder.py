from kernel_client import devices, services, sockets
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import ACCESS_DENIED, INVALID_HANDLE, OK
from kernel_protocol.identity.rights import OBJECT_ENDPOINT, RIGHT_SEND
from kernel_protocol.services.lifecycle import OPERATION_STOP
from kernel_protocol.services.network import (
    KIND_STREAM,
    OPERATION_ENTER,
    OPERATION_EVICT,
    OPERATION_OPEN,
    OPERATION_ROOT,
    OPERATION_STATUS,
    encode_handle,
    encode_request,
    encode_word,
)
from suites.support.expectations import error_code
from suites.support.holdings import held_capabilities

SERVICE = 0
GUESSED_SESSIONS = 8


def reaches_no_device() -> bool:
    holdings = held_capabilities()
    if not holdings:
        return False
    for handle, kind, rights in holdings:
        if kind != OBJECT_ENDPOINT or rights != RIGHT_SEND:
            return False
        if error_code(devices.open_session, handle, 0) == OK:
            return False
        if error_code(devices.list_devices, handle) == OK:
            return False
        if error_code(devices.claim, handle, 1) == OK:
            return False
    return True


def opens_no_socket(service: int) -> bool:
    for instance in range(GUESSED_SESSIONS):
        for session in range(GUESSED_SESSIONS):
            request = encode_request(instance, session, encode_word(KIND_STREAM))
            if error_code(services.call, service, OPERATION_OPEN, request) != INVALID_HANDLE:
                return False
            status = encode_request(instance, session, b"")
            if error_code(services.call, service, OPERATION_STATUS, status) != INVALID_HANDLE:
                return False
    return True


def main() -> bool:
    startup = Startup()
    service = startup.handles[SERVICE]
    return (
        error_code(services.call, service, OPERATION_ENTER) == ACCESS_DENIED
        and error_code(sockets.Network, service, service) == ACCESS_DENIED
        and error_code(services.call, service, OPERATION_ROOT) == ACCESS_DENIED
        and error_code(services.call, service, OPERATION_STOP) == ACCESS_DENIED
        and error_code(services.call, service, OPERATION_EVICT, encode_handle(startup.identity))
        == ACCESS_DENIED
        and opens_no_socket(service)
        and reaches_no_device()
    )
