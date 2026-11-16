import hashlib
import zlib
from dataclasses import asdict, dataclass

GUEST_ADDRESS = "10.0.2.15"
PEER_ADDRESS = "10.0.2.2"
ABSENT_ADDRESS = "10.0.2.99"
PREFIX = 24
GUEST_HARDWARE = "52:54:00:12:34:56"
ECHO_PORT = 7
SINK_PORT = 9
SILENT_PORT = 13
SLOW_PORT = 14
GREETING_PORT = 17
SOURCE_PORT = 19
CLOSED_PORT = 81
INTRUDER_ADDRESS = "10.0.2.77"
INTRUDER_HARDWARE = "02:00:00:00:00:77"
BLOCK_BYTES = 256
COUNTER_BYTES = 4
PATTERN = bytes(range(BLOCK_BYTES))
SHIFT_SEED_FACTOR = 31
SHIFT_INDEX_FACTOR = 17
DIGEST_BYTES = 32
REQUEST_BYTES = 8
GREETING_LINES = 240
GREETING_WORDS_PER_LINE = 5


@dataclass(frozen=True, slots=True)
class LinkPolicy:
    loss: float = 0.0
    duplicate: float = 0.0
    reorder: float = 0.0
    reorder_milliseconds: int = 0
    delay_milliseconds: int = 0


CLEAN = LinkPolicy()


@dataclass(frozen=True, slots=True)
class NetworkPlan:
    uplink: LinkPolicy = CLEAN
    downlink: LinkPolicy = CLEAN
    seed: int = 1

    def to_document(self) -> dict[str, object]:
        return {
            "address": PEER_ADDRESS,
            "prefix": PREFIX,
            "guest": GUEST_ADDRESS,
            "seed": self.seed,
            "uplink": asdict(self.uplink),
            "downlink": asdict(self.downlink),
        }


def stream_block(seed: int, index: int) -> bytes:
    shift = (seed * SHIFT_SEED_FACTOR + index * SHIFT_INDEX_FACTOR) % BLOCK_BYTES
    rotated = PATTERN[shift:] + PATTERN[:shift]
    return index.to_bytes(COUNTER_BYTES, "big") + rotated[COUNTER_BYTES:]


def stream(seed: int, length: int) -> bytes:
    blocks = [
        stream_block(seed, index) for index in range((length + BLOCK_BYTES - 1) // BLOCK_BYTES)
    ]
    return b"".join(blocks)[:length]


def stream_sha256(seed: int, length: int) -> str:
    return hashlib.sha256(stream(seed, length)).hexdigest()


def stream_crc32(seed: int, length: int) -> str:
    return f"{zlib.crc32(stream(seed, length)):08x}"


def greeting() -> bytes:
    lines = [f"line {number:04d} of the greeting\n" for number in range(GREETING_LINES)]
    return "".join(lines).encode("ascii")


def encode_source_request(seed: int, length: int) -> bytes:
    return seed.to_bytes(4, "big") + length.to_bytes(4, "big")


def decode_source_request(request: bytes) -> tuple[int, int]:
    return int.from_bytes(request[:4], "big"), int.from_bytes(request[4:REQUEST_BYTES], "big")
