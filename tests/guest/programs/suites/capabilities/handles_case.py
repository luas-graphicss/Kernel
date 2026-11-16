from kernel_client import capabilities, ipc
from kernel_protocol.errors.codes import INVALID_HANDLE
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.wire.message import Message
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.reporting import Context

SLOT_INDEX_BITS = 24
SLOT_INDEX_MASK = (1 << SLOT_INDEX_BITS) - 1
RESERVED_BIT = 1 << 56
NO_FLAGS = 0


def forged_from(handle: int) -> tuple[tuple[str, int], ...]:
    return (
        ("the null handle", 0),
        ("a handle with reserved bits", handle | RESERVED_BIT),
        ("a handle past the end of the table", handle | SLOT_INDEX_MASK),
        ("a handle of a later generation", handle + (1 << SLOT_INDEX_BITS)),
        ("a handle with every bit set", 0xFFFFFFFFFFFFFFFF),
    )


def run(context: Context, checks: Checks) -> None:
    first = ipc.create_endpoint()
    capabilities.close(first)
    second = ipc.create_endpoint()
    checks.require(
        second != first and second & SLOT_INDEX_MASK == first & SLOT_INDEX_MASK,
        "a reused slot is issued under a new generation",
    )
    stale_uses = (
        ("close", error_code(capabilities.close, first)),
        ("inspect", error_code(capabilities.inspect, first)),
        ("revoke", error_code(capabilities.revoke, first)),
        ("derive", error_code(capabilities.derive, first, RIGHT_SEND)),
        ("send", error_code(ipc.send, first, Message(1, NO_FLAGS, 0, b""))),
        ("receive", error_code(ipc.receive, first)),
    )
    for operation, code in stale_uses:
        checks.require(code == INVALID_HANDLE, f"{operation} refuses the handle of a reused slot")
    for description, forged in forged_from(second):
        checks.require(
            error_code(capabilities.inspect, forged) == INVALID_HANDLE,
            f"{description} names nothing",
        )
    capabilities.close(second)
    checks.require(
        error_code(capabilities.close, second) == INVALID_HANDLE, "a handle is not closed twice"
    )
