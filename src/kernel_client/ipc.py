import _process
from kernel_client.calls import check, scalar
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER, ENDPOINT_CREATE
from kernel_protocol.wire.message import (
    FLAG_REPLY,
    HEADER_BYTES,
    MAX_PAYLOAD_BYTES,
    Message,
    decode_message,
    encode_message,
)

NO_TRANSFER = 0

_storage = bytearray(HEADER_BYTES + MAX_PAYLOAD_BYTES)


class Received:
    def __init__(self, message: Message, sender: int, transferred: int, reply: int) -> None:
        self.message = message
        self.sender = sender
        self.transferred = transferred
        self.reply = reply


def create_endpoint() -> int:
    return scalar(ENDPOINT_CREATE)


def send(
    endpoint: int, message: Message, transfer: int = NO_TRANSFER, deadline: int = DEADLINE_NEVER
) -> None:
    check(_process.send(endpoint, encode_message(message), transfer, deadline))


def receive(endpoint: int, deadline: int = DEADLINE_NEVER) -> Received:
    status, sender, transferred, reply = _process.receive(endpoint, _storage, deadline)
    length = check(status)
    return Received(decode_message(bytes(_storage[:length])), sender, transferred, reply)


def call(
    endpoint: int, message: Message, transfer: int = NO_TRANSFER, deadline: int = DEADLINE_NEVER
) -> tuple[Message, int]:
    status, received = _process.request(
        endpoint, encode_message(message), _storage, transfer, deadline
    )
    length = check(status)
    return decode_message(bytes(_storage[:length])), received


def answer(request: Received, payload: bytes, transfer: int = NO_TRANSFER) -> None:
    response = Message(request.message.operation, FLAG_REPLY, request.message.correlation, payload)
    check(_process.reply(request.reply, encode_message(response), transfer))
