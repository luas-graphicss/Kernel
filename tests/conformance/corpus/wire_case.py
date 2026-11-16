from corpus.digest import Digest
from corpus.failure import require
from corpus.prng import Generator
from kernel_protocol.errors.codes import OK, KernelError
from kernel_protocol.wire.message import (
    HEADER_BYTES,
    MAX_PAYLOAD_BYTES,
    Message,
    decode_message,
    encode_message,
)

MAX_GENERATED_PAYLOAD = 48
VALID_FLAGS = (0, 1, 3)


def random_payload(generator: Generator) -> bytes:
    return bytes([generator.below(256) for _ in range(generator.below(MAX_GENERATED_PAYLOAD + 1))])


def decode_code(buffer: bytes) -> int:
    try:
        decode_message(buffer)
    except KernelError as error:
        return error.code
    return OK


def corrupt(generator: Generator, encoded: bytes) -> bytes:
    choice = generator.below(5)
    if choice == 0:
        return encoded[: generator.below(len(encoded))]
    if choice == 1:
        return encoded + b"\x00"
    mutated = bytearray(encoded)
    if choice == 2:
        mutated[0] = 2
    elif choice == 3:
        mutated[2] = 4 + generator.below(252)
    else:
        mutated[12 + generator.below(4)] = 1 + generator.below(255)
    return bytes(mutated)


def run(seed: int, transitions: int) -> str:
    generator = Generator(seed)
    digest = Digest()

    for _ in range(transitions):
        message = Message(
            operation=generator.next(),
            flags=VALID_FLAGS[generator.below(len(VALID_FLAGS))],
            correlation=(generator.next() << 32) | generator.next(),
            payload=random_payload(generator),
        )
        encoded = encode_message(message)
        require(len(encoded) == HEADER_BYTES + len(message.payload), "encoded length is exact")
        decoded = decode_message(encoded)
        require(decoded.operation == message.operation, "operation survives the round trip")
        require(decoded.flags == message.flags, "flags survive the round trip")
        require(decoded.correlation == message.correlation, "correlation survives the round trip")
        require(decoded.payload == message.payload, "payload survives the round trip")
        digest.add_bytes(encoded)

        code = decode_code(corrupt(generator, encoded))
        require(code != OK, "a corrupted message is rejected")
        digest.add(code)

    oversized = Message(operation=1, flags=0, correlation=1, payload=bytes(MAX_PAYLOAD_BYTES + 1))
    try:
        encode_message(oversized)
    except KernelError as error:
        digest.add(error.code)
    else:
        require(False, "an oversized payload is rejected")
    return digest.hexdigest()
