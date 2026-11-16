import _process
from kernel_client import ipc
from kernel_client.processes import Startup, clock
from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    MESSAGE_TOO_LARGE,
    OK,
    PEER_CLOSED,
    TIMED_OUT,
)
from kernel_protocol.wire.message import FLAG_REPLY, Message, encode_message
from suites.ipc.protocol import NO_FLAGS, OPERATION_RECEIVED, OPERATION_REQUEST, plain, register
from suites.support.expectations import error_code
from suites.support.raw import word

DRAINED_MESSAGES = 65
DRAIN_DELAY_NANOSECONDS = 30000000
OVERSIZED_PAYLOAD_BYTES = 512
NO_TRANSFER = 0


def stay_idle(registrations: int) -> bool:
    register(registrations)
    ipc.receive(ipc.create_endpoint())
    return False


def leave_without_reply(registrations: int) -> bool:
    ipc.receive(register(registrations))
    return True


def hold_then_reply(registrations: int) -> bool:
    endpoint = register(registrations)
    request = ipc.receive(endpoint)
    ipc.send(registrations, plain(OPERATION_RECEIVED))
    ipc.receive(endpoint)
    return error_code(ipc.answer, request, b"") == PEER_CLOSED


def reply_code(request: ipc.Received, flags: int, correlation: int, payload: bytes) -> int:
    response = Message(request.message.operation, flags, correlation, payload)
    return -_process.reply(request.reply, encode_message(response), NO_TRANSFER)


def reply_strictly(registrations: int) -> bool:
    request = ipc.receive(register(registrations))
    correlation = request.message.correlation
    observed = (
        reply_code(request, FLAG_REPLY, correlation + 1, b""),
        reply_code(request, NO_FLAGS, correlation, b""),
        reply_code(request, FLAG_REPLY, correlation, bytes(OVERSIZED_PAYLOAD_BYTES)),
        reply_code(request, FLAG_REPLY, correlation, request.message.payload),
        reply_code(request, FLAG_REPLY, correlation, request.message.payload),
    )
    return observed == (INVALID_ARGUMENT, INVALID_ARGUMENT, MESSAGE_TOO_LARGE, OK, INVALID_HANDLE)


def lend_an_endpoint(registrations: int) -> bool:
    request = ipc.receive(register(registrations))
    ipc.answer(request, b"", ipc.create_endpoint())
    return True


def call_back(registrations: int) -> bool:
    request = ipc.receive(register(registrations))
    code = error_code(ipc.call, request.transferred, plain(OPERATION_REQUEST))
    ipc.answer(request, word(code))
    return True


def drain_in_order(registrations: int) -> bool:
    endpoint = register(registrations)
    silent = ipc.create_endpoint()
    if error_code(ipc.receive, silent, clock() + DRAIN_DELAY_NANOSECONDS) != TIMED_OUT:
        return False
    for expected in range(DRAINED_MESSAGES):
        if ipc.receive(endpoint).message.correlation != expected:
            return False
    return True


ROLES = {
    b"idle": stay_idle,
    b"leaver": leave_without_reply,
    b"holder": hold_then_reply,
    b"strict": reply_strictly,
    b"lender": lend_an_endpoint,
    b"callback": call_back,
    b"drain": drain_in_order,
}


def main() -> bool:
    startup = Startup()
    return ROLES[startup.argument](startup.handles[0])
