from kernel_protocol.errors.codes import TIMED_OUT
from kernel_protocol.wire.message import Message, decode_message, encode_message


class Delivery:
    def __init__(
        self, message: Message, sender: int = 0, transferred: int = 0, reply: int = 0
    ) -> None:
        self.message = message
        self.sender = sender
        self.transferred = transferred
        self.reply = reply


class NativeProcess:
    CALLS = ("startup", "call", "send", "receive", "request", "reply", "spawn", "counters")

    def __init__(self) -> None:
        self.program = "kernel_services.init.main"
        self.argument = b""
        self.handles: tuple[int, ...] = ()
        self.identity = 1
        self.call_results: dict[int, list[int]] = {}
        self.calls: list[tuple[int, int, int]] = []
        self.sent: list[tuple[int, Message, int, int]] = []
        self.deliveries: list[Delivery] = []
        self.requested: list[tuple[int, Message, int, int]] = []
        self.responses: list[Delivery] = []
        self.replied: list[tuple[int, Message, int]] = []
        self.spawn_results: list[int] = []
        self.spawned: list[tuple[int, bytes]] = []
        self.counter_values: tuple[int, ...] | int = ()

    def startup(self) -> tuple[str, bytes, tuple[int, ...], int]:
        return self.program, self.argument, self.handles, self.identity

    def call(self, number: int, first: int = 0, second: int = 0) -> int:
        self.calls.append((number, first, second))
        results = self.call_results.get(number)
        return results.pop(0) if results else 0

    def send(self, endpoint: int, message: bytes, transfer: int, deadline: int) -> int:
        self.sent.append((endpoint, decode_message(message), transfer, deadline))
        return 0

    def receive(self, endpoint: int, buffer: bytearray, deadline: int) -> tuple[int, int, int, int]:
        if not self.deliveries:
            return -TIMED_OUT, 0, 0, 0
        delivery = self.deliveries.pop(0)
        length = self._store(buffer, delivery.message)
        return length, delivery.sender, delivery.transferred, delivery.reply

    def request(
        self, endpoint: int, message: bytes, response: bytearray, transfer: int, deadline: int
    ) -> tuple[int, int]:
        self.requested.append((endpoint, decode_message(message), transfer, deadline))
        if not self.responses:
            return -TIMED_OUT, 0
        delivery = self.responses.pop(0)
        return self._store(response, delivery.message), delivery.transferred

    def reply(self, reply: int, message: bytes, transfer: int) -> int:
        self.replied.append((reply, decode_message(message), transfer))
        return 0

    def spawn(self, system: int, request: bytes) -> int:
        self.spawned.append((system, bytes(request)))
        return self.spawn_results.pop(0)

    def counters(self, system: int) -> tuple[int, ...] | int:
        return self.counter_values

    def _store(self, buffer: bytearray, message: Message) -> int:
        encoded = encode_message(message)
        buffer[: len(encoded)] = encoded
        return len(encoded)
