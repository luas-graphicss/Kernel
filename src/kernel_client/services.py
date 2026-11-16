import _process
from kernel_client import capabilities, ipc
from kernel_client.calls import check
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    PEER_CLOSED,
    UNSUPPORTED,
    KernelError,
)
from kernel_protocol.services.lifecycle import (
    OPERATION_REGISTER,
    OPERATION_STOP,
    decode_error,
    encode_error,
)
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER
from kernel_protocol.wire.message import FLAG_ERROR, FLAG_REPLY, Message, encode_message

NO_FLAGS = 0
REGISTRATION_CORRELATION = 1
REFUSAL = "service refused the request"


class Correlations:
    def __init__(self) -> None:
        self._last = REGISTRATION_CORRELATION

    def next(self) -> int:
        self._last += 1
        return self._last


class Reply:
    def __init__(self, payload: bytes = b"", transfer: int = ipc.NO_TRANSFER) -> None:
        self.payload = payload
        self.transfer = transfer


class Service:
    def handle(self, request: ipc.Received) -> Reply:
        raise KernelError(UNSUPPORTED, "operation is not part of the service")

    def takes_capability(self, operation: int) -> bool:
        return False

    def stop(self) -> None:
        return


_correlations = Correlations()


def call(
    endpoint: int,
    operation: int,
    payload: bytes = b"",
    transfer: int = ipc.NO_TRANSFER,
    deadline: int = DEADLINE_NEVER,
) -> tuple[bytes, int]:
    request = Message(operation, NO_FLAGS, _correlations.next(), payload)
    response, received = ipc.call(endpoint, request, transfer, deadline)
    if response.flags & FLAG_ERROR:
        raise KernelError(decode_error(response.payload), REFUSAL)
    return response.payload, received


def note(endpoint: int, operation: int, payload: bytes = b"") -> None:
    ipc.send(endpoint, Message(operation, NO_FLAGS, _correlations.next(), payload))


def register(registration: int, endpoint: int, payload: bytes = b"") -> None:
    announcement = Message(OPERATION_REGISTER, NO_FLAGS, REGISTRATION_CORRELATION, payload)
    ipc.send(registration, announcement, endpoint)


def discard_transfer(request: ipc.Received) -> None:
    if request.transferred != ipc.NO_TRANSFER:
        capabilities.close(request.transferred)


def respond(request: ipc.Received, reply: Reply) -> None:
    try:
        ipc.answer(request, reply.payload, reply.transfer)
    except KernelError as error:
        if error.code != PEER_CLOSED:
            raise


def refuse(request: ipc.Received, code: int) -> None:
    message = request.message
    response = Message(
        message.operation, FLAG_REPLY | FLAG_ERROR, message.correlation, encode_error(code)
    )
    status = _process.reply(request.reply, encode_message(response), ipc.NO_TRANSFER)
    if status != -PEER_CLOSED:
        check(status)


def answer(request: ipc.Received, service: Service) -> None:
    carries = request.transferred != ipc.NO_TRANSFER
    if carries and not service.takes_capability(request.message.operation):
        discard_transfer(request)
        refuse(request, INVALID_ARGUMENT)
        return
    try:
        reply = service.handle(request)
    except KernelError as error:
        refuse(request, error.code)
        return
    respond(request, reply)


def serve(endpoint: int, service: Service, supervisor: int) -> bool:
    while True:
        request = ipc.receive(endpoint)
        if request.reply == 0:
            discard_transfer(request)
        elif request.message.operation != OPERATION_STOP:
            answer(request, service)
        elif request.sender != supervisor:
            refuse(request, ACCESS_DENIED)
        else:
            service.stop()
            respond(request, Reply())
            return True
