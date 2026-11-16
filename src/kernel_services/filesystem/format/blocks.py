from kernel_protocol.errors.codes import LIMIT_EXCEEDED, KernelError
from kernel_services.filesystem.format.codec import corrupted, get, put
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    HEADER_BYTES,
    HEADER_GENERATION,
    HEADER_PAYLOAD_BYTES,
    PAYLOAD_BYTES,
)

MAGIC_BYTES = 4


def encode_block(magic: bytes, generation: int, payload: bytes) -> bytes:
    if len(payload) > PAYLOAD_BYTES:
        raise KernelError(LIMIT_EXCEEDED, "metadata does not fit in one block")
    header = magic + put(len(payload), 4) + put(generation, 8)
    return header + payload + bytes(PAYLOAD_BYTES - len(payload))


def decode_block(block: bytes, magic: bytes, newest_generation: int) -> tuple[int, bytes]:
    payload_bytes = get(block, HEADER_PAYLOAD_BYTES, 4)
    generation = get(block, HEADER_GENERATION, 8)
    if len(block) != BLOCK_BYTES or block[:MAGIC_BYTES] != magic:
        raise corrupted("block is not of the type its pointer expects")
    if payload_bytes > PAYLOAD_BYTES:
        raise corrupted("block declares more payload than it can hold")
    if generation == 0 or generation > newest_generation:
        raise corrupted("block is newer than the block that points to it")
    if block[HEADER_BYTES + payload_bytes :] != bytes(PAYLOAD_BYTES - payload_bytes):
        raise corrupted("block carries data after its payload")
    return generation, block[HEADER_BYTES : HEADER_BYTES + payload_bytes]
