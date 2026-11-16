from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.wire.message import MAX_PAYLOAD_BYTES, pack_unsigned, unpack_unsigned

OPERATION_ROOT = 16
OPERATION_EVICT = 17
OPERATION_ENTER = 18
OPERATION_LEAVE = 19
OPERATION_RESTRICT = 20
OPERATION_STATUS = 21
OPERATION_NEIGHBORS = 22
OPERATION_ECHO = 23
OPERATION_OPEN = 24
OPERATION_BIND = 25
OPERATION_LISTEN = 26
OPERATION_ACCEPT = 27
OPERATION_CONNECT = 28
OPERATION_SEND = 29
OPERATION_RECEIVE = 30
OPERATION_SEND_TO = 31
OPERATION_RECEIVE_FROM = 32
OPERATION_FINISH = 33
OPERATION_CLOSE = 34
OPERATION_DESCRIBE = 35
OPERATION_REVOKE = 36

ACCESS_CONNECT = 0x01
ACCESS_LISTEN = 0x02
ACCESS_DATAGRAM = 0x04
ACCESS_ECHO = 0x08
ACCESS_INSPECT = 0x10
ACCESS_DELEGATE = 0x20
ACCESS_ALL = 0x3F
ACCESS_NAMES = (
    ("connect", ACCESS_CONNECT),
    ("listen", ACCESS_LISTEN),
    ("datagram", ACCESS_DATAGRAM),
    ("echo", ACCESS_ECHO),
    ("inspect", ACCESS_INSPECT),
    ("delegate", ACCESS_DELEGATE),
)

KIND_STREAM = 1
KIND_DATAGRAM = 2

STATE_NEW = 0
STATE_BOUND = 1
STATE_LISTENING = 2
STATE_CONNECTING = 3
STATE_CONNECTED = 4
STATE_PEER_FINISHED = 5
STATE_FINISHED = 6
STATE_CLOSED = 7
STATE_NAMES = (
    "new",
    "bound",
    "listening",
    "connecting",
    "connected",
    "peer-finished",
    "finished",
    "closed",
)

WAIT_FOREVER = 0xFFFFFFFFFFFFFFFF
NO_WAIT = 0
ANY_PORT = 0
HIGHEST_PORT = 0xFFFF
MAX_TRANSFER_BYTES = MAX_PAYLOAD_BYTES - 64
MAX_ECHO_BYTES = 1024
MAX_BACKLOG = 8
MAX_NEIGHBORS = 32

HARDWARE_BYTES = 6
SUBJECT_BYTES = 16
SESSION_BYTES = 20
INTERFACE_BYTES = 32
NEIGHBOR_BYTES = 10
ECHO_BYTES = 14
PEER_BYTES = 6
ACCEPTED_BYTES = 14
CONNECT_BYTES = 14
WAIT_BYTES = 8
RECEIVE_BYTES = 12
SENDER_BYTES = 10
DESCRIPTION_BYTES = 22
COUNTER_BYTES = 8


class InterfaceStatus:
    def __init__(
        self,
        hardware: bytes,
        address: int,
        prefix: int,
        gateway: int,
        mtu: int,
        is_linked: bool,
        sockets: int,
        connections: int,
        buffered_bytes: int,
        resets: int,
        counters: list[int],
    ) -> None:
        self.hardware = hardware
        self.address = address
        self.prefix = prefix
        self.gateway = gateway
        self.mtu = mtu
        self.is_linked = is_linked
        self.sockets = sockets
        self.connections = connections
        self.buffered_bytes = buffered_bytes
        self.resets = resets
        self.counters = counters


class SocketDescription:
    def __init__(
        self,
        kind: int,
        state: int,
        local_port: int,
        remote_address: int,
        remote_port: int,
        readable_bytes: int,
        writable_bytes: int,
        error: int,
    ) -> None:
        self.kind = kind
        self.state = state
        self.local_port = local_port
        self.remote_address = remote_address
        self.remote_port = remote_port
        self.readable_bytes = readable_bytes
        self.writable_bytes = writable_bytes
        self.error = error


def malformed() -> KernelError:
    return KernelError(
        INVALID_ARGUMENT, "network request does not have the layout of its operation"
    )


def exactly(payload: bytes, size: int) -> bytes:
    if len(payload) != size:
        raise malformed()
    return payload


def at_least(payload: bytes, size: int) -> bytes:
    if len(payload) < size:
        raise malformed()
    return payload


def encode_request(instance: int, subject: int, body: bytes = b"") -> bytes:
    return pack_unsigned(instance, 8) + pack_unsigned(subject, 8) + body


def decode_request(payload: bytes) -> tuple[int, int, bytes]:
    at_least(payload, SUBJECT_BYTES)
    return (
        unpack_unsigned(payload, 0, 8),
        unpack_unsigned(payload, 8, 16),
        payload[SUBJECT_BYTES:],
    )


def encode_session(instance: int, session: int, rights: int) -> bytes:
    return pack_unsigned(instance, 8) + pack_unsigned(session, 8) + pack_unsigned(rights, 4)


def decode_session(payload: bytes) -> tuple[int, int, int]:
    exactly(payload, SESSION_BYTES)
    return (
        unpack_unsigned(payload, 0, 8),
        unpack_unsigned(payload, 8, 16),
        unpack_unsigned(payload, 16, 20),
    )


def encode_word(value: int) -> bytes:
    return pack_unsigned(value, 4)


def decode_word(body: bytes) -> int:
    return unpack_unsigned(exactly(body, 4), 0, 4)


def encode_handle(handle: int) -> bytes:
    return pack_unsigned(handle, 8)


def decode_handle(body: bytes) -> int:
    return unpack_unsigned(exactly(body, 8), 0, 8)


def encode_port(port: int) -> bytes:
    return pack_unsigned(port, 2)


def decode_port(body: bytes) -> int:
    return unpack_unsigned(exactly(body, 2), 0, 2)


def encode_wait(timeout_nanoseconds: int) -> bytes:
    return pack_unsigned(timeout_nanoseconds, 8)


def decode_wait(body: bytes) -> int:
    return unpack_unsigned(exactly(body, WAIT_BYTES), 0, 8)


def encode_peer(address: int, port: int) -> bytes:
    return pack_unsigned(address, 4) + pack_unsigned(port, 2)


def encode_connect(address: int, port: int, timeout_nanoseconds: int) -> bytes:
    return encode_peer(address, port) + pack_unsigned(timeout_nanoseconds, 8)


def decode_connect(body: bytes) -> tuple[int, int, int]:
    exactly(body, CONNECT_BYTES)
    return (
        unpack_unsigned(body, 0, 4),
        unpack_unsigned(body, 4, 6),
        unpack_unsigned(body, 6, 14),
    )


def encode_accepted(handle: int, address: int, port: int) -> bytes:
    return pack_unsigned(handle, 8) + encode_peer(address, port)


def decode_accepted(payload: bytes) -> tuple[int, int, int]:
    exactly(payload, ACCEPTED_BYTES)
    return (
        unpack_unsigned(payload, 0, 8),
        unpack_unsigned(payload, 8, 12),
        unpack_unsigned(payload, 12, 14),
    )


def encode_send(timeout_nanoseconds: int, data: bytes) -> bytes:
    return pack_unsigned(timeout_nanoseconds, 8) + data


def decode_send(body: bytes) -> tuple[int, bytes]:
    at_least(body, WAIT_BYTES)
    return unpack_unsigned(body, 0, 8), body[WAIT_BYTES:]


def encode_receive(timeout_nanoseconds: int, limit: int) -> bytes:
    return pack_unsigned(timeout_nanoseconds, 8) + pack_unsigned(limit, 4)


def decode_receive(body: bytes) -> tuple[int, int]:
    exactly(body, RECEIVE_BYTES)
    return unpack_unsigned(body, 0, 8), unpack_unsigned(body, 8, 12)


def encode_send_to(address: int, port: int, data: bytes) -> bytes:
    return encode_peer(address, port) + data


def decode_send_to(body: bytes) -> tuple[int, int, bytes]:
    at_least(body, PEER_BYTES)
    return unpack_unsigned(body, 0, 4), unpack_unsigned(body, 4, 6), body[PEER_BYTES:]


def encode_received_from(address: int, port: int, datagram_bytes: int, data: bytes) -> bytes:
    return encode_peer(address, port) + pack_unsigned(datagram_bytes, 4) + data


def decode_received_from(payload: bytes) -> tuple[int, int, int, bytes]:
    at_least(payload, SENDER_BYTES)
    return (
        unpack_unsigned(payload, 0, 4),
        unpack_unsigned(payload, 4, 6),
        unpack_unsigned(payload, 6, 10),
        payload[SENDER_BYTES:],
    )


def encode_echo(address: int, timeout_nanoseconds: int, data_bytes: int) -> bytes:
    return (
        pack_unsigned(address, 4)
        + pack_unsigned(timeout_nanoseconds, 8)
        + pack_unsigned(data_bytes, 2)
    )


def decode_echo(body: bytes) -> tuple[int, int, int]:
    exactly(body, ECHO_BYTES)
    return (
        unpack_unsigned(body, 0, 4),
        unpack_unsigned(body, 4, 12),
        unpack_unsigned(body, 12, 14),
    )


def encode_duration(nanoseconds: int) -> bytes:
    return pack_unsigned(nanoseconds, 8)


def decode_duration(payload: bytes) -> int:
    return unpack_unsigned(exactly(payload, 8), 0, 8)


def encode_interface(status: InterfaceStatus) -> bytes:
    fixed = (
        status.hardware
        + pack_unsigned(status.address, 4)
        + pack_unsigned(status.gateway, 4)
        + pack_unsigned(status.mtu, 2)
        + pack_unsigned(status.prefix, 1)
        + pack_unsigned(1 if status.is_linked else 0, 1)
        + pack_unsigned(status.sockets, 2)
        + pack_unsigned(status.connections, 2)
        + pack_unsigned(status.buffered_bytes, 4)
        + pack_unsigned(status.resets, 4)
        + pack_unsigned(len(status.counters), 2)
    )
    return fixed + b"".join([pack_unsigned(value, COUNTER_BYTES) for value in status.counters])


def decode_interface(payload: bytes) -> InterfaceStatus:
    at_least(payload, INTERFACE_BYTES)
    count = unpack_unsigned(payload, 30, 32)
    exactly(payload, INTERFACE_BYTES + count * COUNTER_BYTES)
    counters = []
    for index in range(count):
        start = INTERFACE_BYTES + index * COUNTER_BYTES
        counters.append(unpack_unsigned(payload, start, start + COUNTER_BYTES))
    return InterfaceStatus(
        hardware=payload[:HARDWARE_BYTES],
        address=unpack_unsigned(payload, 6, 10),
        prefix=payload[16],
        gateway=unpack_unsigned(payload, 10, 14),
        mtu=unpack_unsigned(payload, 14, 16),
        is_linked=payload[17] != 0,
        sockets=unpack_unsigned(payload, 18, 20),
        connections=unpack_unsigned(payload, 20, 22),
        buffered_bytes=unpack_unsigned(payload, 22, 26),
        resets=unpack_unsigned(payload, 26, 30),
        counters=counters,
    )


def encode_neighbors(neighbors: list[tuple[int, bytes]]) -> bytes:
    return b"".join([pack_unsigned(address, 4) + hardware for address, hardware in neighbors])


def decode_neighbors(payload: bytes) -> list[tuple[int, bytes]]:
    if len(payload) % NEIGHBOR_BYTES:
        raise malformed()
    neighbors = []
    for start in range(0, len(payload), NEIGHBOR_BYTES):
        neighbors.append(
            (
                unpack_unsigned(payload, start, start + 4),
                payload[start + 4 : start + NEIGHBOR_BYTES],
            )
        )
    return neighbors


def encode_description(description: SocketDescription) -> bytes:
    return (
        pack_unsigned(description.kind, 1)
        + pack_unsigned(description.state, 1)
        + pack_unsigned(description.local_port, 2)
        + pack_unsigned(description.remote_address, 4)
        + pack_unsigned(description.remote_port, 2)
        + pack_unsigned(description.readable_bytes, 4)
        + pack_unsigned(description.writable_bytes, 4)
        + pack_unsigned(description.error, 4)
    )


def decode_description(payload: bytes) -> SocketDescription:
    exactly(payload, DESCRIPTION_BYTES)
    return SocketDescription(
        kind=payload[0],
        state=payload[1],
        local_port=unpack_unsigned(payload, 2, 4),
        remote_address=unpack_unsigned(payload, 4, 8),
        remote_port=unpack_unsigned(payload, 8, 10),
        readable_bytes=unpack_unsigned(payload, 10, 14),
        writable_bytes=unpack_unsigned(payload, 14, 18),
        error=unpack_unsigned(payload, 18, 22),
    )


def parse_access(names: str) -> int:
    rights = 0
    for name in names.split(" "):
        if not name:
            continue
        granted = 0
        for known, right in ACCESS_NAMES:
            if known == name:
                granted = right
        if granted == 0:
            raise KernelError(INVALID_ARGUMENT, "unknown network access right")
        rights |= granted
    return rights
