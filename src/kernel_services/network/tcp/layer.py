from kernel_protocol.errors.codes import ALREADY_EXISTS, LIMIT_EXCEEDED, KernelError
from kernel_services.network.counters import (
    TCP_BACKLOG_FULL,
    TCP_CONNECTIONS_FAILED,
    TCP_CONNECTIONS_OPENED,
    TCP_NO_SOCKET,
    TCP_RESETS_SENT,
    Counters,
)
from kernel_services.network.icmp.limiter import RateLimiter
from kernel_services.network.icmp.message import (
    CODE_FRAGMENTATION_NEEDED,
    CODE_PORT_UNREACHABLE,
    CODE_PROTOCOL_UNREACHABLE,
)
from kernel_services.network.ipv4.header import PROTOCOL_TCP
from kernel_services.network.limits import EPHEMERAL_FIRST_PORT, EPHEMERAL_LAST_PORT
from kernel_services.network.tcp.connection import CLOSED, TIME_WAIT, Connection
from kernel_services.network.tcp.listener import Listener
from kernel_services.network.tcp.segment import (
    FLAG_ACK,
    FLAG_RST,
    FLAG_SYN,
    NO_SEGMENT_SIZE,
    Segment,
    decode_segment,
    encode_segment,
)
from kernel_services.network.tcp.sequence import MASK, advance
from kernel_services.network.tcp.settings import Settings

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

SEQUENCE_BYTES = 4
PORT_BYTES = 2
EPHEMERAL_PORTS = EPHEMERAL_LAST_PORT - EPHEMERAL_FIRST_PORT + 1
HARD_REFUSALS = (CODE_PROTOCOL_UNREACHABLE, CODE_PORT_UNREACHABLE)


class TcpLayer:
    def __init__(
        self,
        local_address: int,
        send_datagram: "Callable[[int, int, bytes, bool], int]",
        settings: Settings,
        entropy: "Callable[[int], bytes]",
        counters: Counters,
        max_connections: int,
        reset_limiter: RateLimiter,
    ) -> None:
        self._local_address = local_address
        self._send_datagram = send_datagram
        self._settings = settings
        self._entropy = entropy
        self._counters = counters
        self._max_connections = max_connections
        self._reset_limiter = reset_limiter
        self._connections: dict[tuple[int, int, int], Connection] = {}
        self._listeners: dict[int, Listener] = {}
        self._ports: dict[int, int] = {}

    def connection_count(self) -> int:
        lingering = [held for held in self._connections.values() if held.state == TIME_WAIT]
        return len(self._connections) - len(lingering)

    def connect(self, remote_address: int, remote_port: int, now: int) -> Connection:
        if len(self._connections) >= self._max_connections:
            raise KernelError(LIMIT_EXCEEDED, "the connection table is full")
        connection = self._create(self._ephemeral_port(), remote_address, remote_port)
        connection.open_active(now)
        return connection

    def listen(self, port: int, backlog: int) -> Listener:
        if port in self._listeners or port in self._ports:
            raise KernelError(ALREADY_EXISTS, "the port already has a socket")
        listener = Listener(port, backlog)
        self._listeners[port] = listener
        return listener

    def stop_listening(self, listener: Listener) -> None:
        if self._listeners.get(listener.port) is listener:
            del self._listeners[listener.port]
        for connection in listener.pending + listener.ready:
            self.release(connection)
        listener.pending = []
        listener.ready = []

    def release(self, connection: Connection) -> None:
        connection.abort()
        connection.discard_input()
        self._forget(connection)

    def segment_arrives(self, source: int, payload: bytes, now: int) -> None:
        segment = decode_segment(payload, source, self._local_address, self._counters)
        if segment is None:
            return
        key = (segment.destination_port, source, segment.source_port)
        connection = self._connections.get(key)
        if connection is not None:
            connection.segment_arrives(segment, now)
            self._settle(connection)
            return
        listener = self._listeners.get(segment.destination_port)
        opens = segment.flags & (FLAG_SYN | FLAG_ACK | FLAG_RST) == FLAG_SYN
        if listener is not None and opens:
            self._admit(listener, source, segment, now)
        else:
            self._refuse(source, segment, now)

    def path_reports(
        self, remote_address: int, transport: bytes, code: int, next_hop_bytes: int, now: int
    ) -> None:
        local_port = int.from_bytes(transport[:PORT_BYTES], "big")
        remote_port = int.from_bytes(transport[PORT_BYTES : 2 * PORT_BYTES], "big")
        connection = self._connections.get((local_port, remote_address, remote_port))
        if connection is None:
            return
        if code == CODE_FRAGMENTATION_NEEDED:
            connection.path_narrowed(next_hop_bytes, now)
        elif code in HARD_REFUSALS:
            connection.refused_by_path()
        else:
            connection.note_unreachable()
        self._settle(connection)

    def hop_unreachable(self, next_hop_of: "Callable[[int], int]", hop: int) -> None:
        for connection in list(self._connections.values()):
            if next_hop_of(connection.remote_address) == hop:
                connection.hop_unresolved()
                self._settle(connection)

    def timers_expire(self, now: int) -> None:
        for connection in list(self._connections.values()):
            if connection.next_deadline() <= now:
                connection.timers_expire(now)
                self._settle(connection)

    def next_deadline(self, none: int) -> int:
        deadline = none
        for connection in self._connections.values():
            if connection.next_deadline() < deadline:
                deadline = connection.next_deadline()
        return deadline

    def abort_all(self) -> None:
        for listener in list(self._listeners.values()):
            self.stop_listening(listener)
        for connection in list(self._connections.values()):
            self.release(connection)

    def _create(self, local_port: int, remote_address: int, remote_port: int) -> Connection:
        sequence = int.from_bytes(self._entropy(SEQUENCE_BYTES), "big") & MASK
        connection = Connection(
            local_port,
            remote_address,
            remote_port,
            sequence,
            self._settings,
            self._emit,
            self._counters,
        )
        self._connections[(local_port, remote_address, remote_port)] = connection
        self._ports[local_port] = self._ports.get(local_port, 0) + 1
        self._counters.count(TCP_CONNECTIONS_OPENED)
        return connection

    def _admit(self, listener: Listener, source: int, segment: Segment, now: int) -> None:
        if not listener.has_room() or len(self._connections) >= self._max_connections:
            self._counters.count(TCP_BACKLOG_FULL)
            return
        connection = self._create(listener.port, source, segment.source_port)
        listener.pending.append(connection)
        connection.open_passive(segment, now)

    def _refuse(self, source: int, segment: Segment, now: int) -> None:
        self._counters.count(TCP_NO_SOCKET)
        if segment.has(FLAG_RST) or not self._reset_limiter.allow(now):
            return
        if segment.has(FLAG_ACK):
            sequence = segment.acknowledgment
            acknowledgment = 0
            flags = FLAG_RST
        else:
            sequence = 0
            acknowledgment = advance(segment.sequence, segment.length())
            flags = FLAG_RST | FLAG_ACK
        self._counters.count(TCP_RESETS_SENT)
        reset = Segment(
            segment.destination_port,
            segment.source_port,
            sequence,
            acknowledgment,
            flags,
            0,
            NO_SEGMENT_SIZE,
            b"",
        )
        self._send_datagram(
            source, PROTOCOL_TCP, encode_segment(self._local_address, source, reset), True
        )

    def _settle(self, connection: Connection) -> None:
        if connection.is_passive:
            listener = self._listeners.get(connection.local_port)
            if listener is not None:
                listener.settle(connection)
        if connection.state == CLOSED:
            if connection.error != 0:
                self._counters.count(TCP_CONNECTIONS_FAILED)
            self._forget(connection)

    def _forget(self, connection: Connection) -> None:
        key = (connection.local_port, connection.remote_address, connection.remote_port)
        if self._connections.get(key) is not connection:
            return
        del self._connections[key]
        remaining = self._ports[connection.local_port] - 1
        if remaining == 0:
            del self._ports[connection.local_port]
        else:
            self._ports[connection.local_port] = remaining

    def _ephemeral_port(self) -> int:
        offset = int.from_bytes(self._entropy(PORT_BYTES), "big") % EPHEMERAL_PORTS
        for attempt in range(EPHEMERAL_PORTS):
            port = EPHEMERAL_FIRST_PORT + (offset + attempt) % EPHEMERAL_PORTS
            if port not in self._ports and port not in self._listeners:
                return port
        raise KernelError(LIMIT_EXCEEDED, "no ephemeral port is free")

    def _emit(self, connection: Connection, segment: Segment) -> None:
        encoded = encode_segment(self._local_address, connection.remote_address, segment)
        self._send_datagram(connection.remote_address, PROTOCOL_TCP, encoded, True)
