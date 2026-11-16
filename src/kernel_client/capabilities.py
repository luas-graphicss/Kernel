from kernel_client.calls import scalar
from kernel_protocol.identity.rights import unpack_inspection
from kernel_protocol.syscalls.numbers import (
    CAPABILITY_CLOSE,
    CAPABILITY_DERIVE,
    CAPABILITY_INSPECT,
    CAPABILITY_REVOKE,
)


def close(handle: int) -> None:
    scalar(CAPABILITY_CLOSE, handle)


def derive(handle: int, rights: int) -> int:
    return scalar(CAPABILITY_DERIVE, handle, rights)


def revoke(handle: int) -> int:
    return scalar(CAPABILITY_REVOKE, handle)


def inspect(handle: int) -> tuple[int, int, int]:
    return unpack_inspection(scalar(CAPABILITY_INSPECT, handle))
