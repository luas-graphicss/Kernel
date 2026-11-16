from kernel_protocol.errors.codes import (
    ALREADY_EXISTS,
    CONNECTION_REFUSED,
    LIMIT_EXCEEDED,
    OK,
    UNREACHABLE,
    KernelError,
)
from kernel_services.network.budget import BufferBudget
from kernel_services.network.counters import (
    UDP_DELIVERED,
    UDP_NO_LISTENER,
    UDP_QUEUE_FULL,
    Counters,
)
from kernel_services.network.icmp.message import CODE_PORT_UNREACHABLE
from kernel_services.network.ipv4.header import PROTOCOL_UDP
from kernel_services.network.limits import EPHEMERAL_FIRST_PORT, EPHEMERAL_LAST_PORT
from kernel_services.network.udp.datagram import UdpDatagram, encode_datagram

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

PORT_BYTES = 2
EPHEMERAL_PORTS = EPHEMERAL_LAST_PORT - EPHEMERAL_FIRST_PORT + 1
ANY_PORT = 0


class UdpPort:
    def __init__(
        self, number: int, max_datagrams: int, max_bytes: int, budget: BufferBudget
    ) -> None:
        self.number = number
        self.error = OK
        self.dropped = 0
        self.queued_bytes = 0
        self._max_datagrams = max_datagrams
        self._max_bytes = max_bytes
        self._budget = budget
        self._queue: list[tuple[int, int, bytes]] = []

    def pending(self) -> int:
        return len(self._queue)

    def offer(self, source: int, source_port: int, data: bytes) -> bool:
        if len(self._queue) == self._max_datagrams:
            return False
        if self.queued_bytes + len(data) > self._max_bytes or not self._budget.reserve(len(data)):
            return False
        self._queue.append((source, source_port, data))
        self.queued_bytes += len(data)
        return True

    def first(self) -> tuple[int, int, bytes] | None:
        if not self._queue:
            return None
        return self._queue[0]

    def take(self) -> tuple[int, int, bytes] | None:
        if not self._queue:
            return None
        taken = self._queue.pop(0)
        self.queued_bytes -= len(taken[2])
        self._budget.release(len(taken[2]))
        return taken

    def take_error(self) -> int:
        error = self.error
        self.error = OK
        return error

    def discard(self) -> None:
        self._budget.release(self.queued_bytes)
        self._queue = []
        self.queued_bytes = 0


class UdpLayer:
    def __init__(
        self,
        local_address: int,
        send_datagram: "Callable[[int, int, bytes, bool], int]",
        entropy: "Callable[[int], bytes]",
        counters: Counters,
        budget: BufferBudget,
        max_datagrams: int,
        max_bytes: int,
    ) -> None:
        self._local_address = local_address
        self._send_datagram = send_datagram
        self._entropy = entropy
        self._counters = counters
        self._budget = budget
        self._max_datagrams = max_datagrams
        self._max_bytes = max_bytes
        self._ports: dict[int, UdpPort] = {}

    def bind(self, number: int) -> UdpPort:
        if number == ANY_PORT:
            number = self._ephemeral_port()
        elif number in self._ports:
            raise KernelError(ALREADY_EXISTS, "the port already has a socket")
        port = UdpPort(number, self._max_datagrams, self._max_bytes, self._budget)
        self._ports[number] = port
        return port

    def unbind(self, port: UdpPort) -> None:
        port.discard()
        if self._ports.get(port.number) is port:
            del self._ports[port.number]

    def send(self, port: UdpPort, destination: int, destination_port: int, data: bytes) -> int:
        encoded = encode_datagram(
            self._local_address, destination, port.number, destination_port, data
        )
        return self._send_datagram(destination, PROTOCOL_UDP, encoded, False)

    def datagram_arrives(self, source: int, datagram: UdpDatagram) -> bool:
        port = self._ports.get(datagram.destination_port)
        if port is None:
            self._counters.count(UDP_NO_LISTENER)
            return False
        if port.offer(source, datagram.source_port, datagram.data):
            self._counters.count(UDP_DELIVERED)
        else:
            port.dropped += 1
            self._counters.count(UDP_QUEUE_FULL)
        return True

    def path_reports(self, transport: bytes, code: int) -> None:
        port = self._ports.get(int.from_bytes(transport[:PORT_BYTES], "big"))
        if port is not None:
            port.error = CONNECTION_REFUSED if code == CODE_PORT_UNREACHABLE else UNREACHABLE

    def unbind_all(self) -> None:
        for port in list(self._ports.values()):
            self.unbind(port)

    def _ephemeral_port(self) -> int:
        offset = int.from_bytes(self._entropy(PORT_BYTES), "big") % EPHEMERAL_PORTS
        for attempt in range(EPHEMERAL_PORTS):
            number = EPHEMERAL_FIRST_PORT + (offset + attempt) % EPHEMERAL_PORTS
            if number not in self._ports:
                return number
        raise KernelError(LIMIT_EXCEEDED, "no ephemeral port is free")
