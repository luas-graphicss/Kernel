from kernel_protocol.errors.codes import CORRUPTED, KernelError


def put(value: int, width: int) -> bytes:
    return value.to_bytes(width, "little")


def get(buffer: bytes, offset: int, width: int) -> int:
    return int.from_bytes(buffer[offset : offset + width], "little")


def corrupted(detail: str) -> KernelError:
    return KernelError(CORRUPTED, detail)


def smaller(first: int, second: int) -> int:
    return first if first < second else second


def larger(first: int, second: int) -> int:
    return first if first > second else second
