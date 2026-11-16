import _process
from kernel_client.sockets import StreamSocket
from suites.network.peer import DIGEST_BYTES, SECOND

BLOCK_BYTES = 256
COUNTER_BYTES = 4
PATTERN = bytes(range(BLOCK_BYTES))
SHIFT_SEED_FACTOR = 31
SHIFT_INDEX_FACTOR = 17
BLOCKS_PER_WRITE = 8
RECEIVE_BYTES = 4000
TRANSFER_TIMEOUT = 60 * SECOND
HEX_DIGITS = "0123456789abcdef"


def stream_block(seed: int, index: int) -> bytes:
    shift = (seed * SHIFT_SEED_FACTOR + index * SHIFT_INDEX_FACTOR) % BLOCK_BYTES
    rotated = PATTERN[shift:] + PATTERN[:shift]
    return index.to_bytes(COUNTER_BYTES, "big") + rotated[COUNTER_BYTES:]


def stream_part(seed: int, first_block: int, blocks: int) -> bytes:
    return b"".join([stream_block(seed, first_block + index) for index in range(blocks)])


def to_hex(data: bytes) -> str:
    return "".join([HEX_DIGITS[value >> 4] + HEX_DIGITS[value & 0x0F] for value in data])


def encode_source_request(seed: int, length: int) -> bytes:
    return seed.to_bytes(4, "big") + length.to_bytes(4, "big")


def send_stream(socket: StreamSocket, seed: int, length: int) -> None:
    blocks = length // BLOCK_BYTES
    sent = 0
    while sent < blocks:
        count = blocks - sent
        if count > BLOCKS_PER_WRITE:
            count = BLOCKS_PER_WRITE
        socket.send_all(stream_part(seed, sent, count), TRANSFER_TIMEOUT)
        sent += count


def receive_exactly(socket: StreamSocket, length: int) -> bytes:
    parts = []
    received = 0
    while received < length:
        part = socket.receive(length - received, TRANSFER_TIMEOUT)
        if not part:
            break
        parts.append(part)
        received += len(part)
    return b"".join(parts)


def receive_digest(socket: StreamSocket) -> str:
    return to_hex(receive_exactly(socket, DIGEST_BYTES))


def receive_checksum(socket: StreamSocket) -> tuple[int, int]:
    checksum = 0
    received = 0
    while True:
        part = socket.receive(RECEIVE_BYTES, TRANSFER_TIMEOUT)
        if not part:
            return received, checksum
        checksum = _process.crc32(part, checksum)
        received += len(part)


def format_checksum(checksum: int) -> str:
    return to_hex(checksum.to_bytes(4, "big"))
