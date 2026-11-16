from kernel_client import capabilities, memory
from kernel_protocol.errors.codes import INVALID_ARGUMENT, LIMIT_EXCEEDED
from kernel_protocol.identity.rights import RIGHT_MAP, RIGHT_READ, RIGHT_WRITE
from kernel_protocol.processes.status import BUFFER_MAX_BYTES
from kernel_protocol.syscalls.numbers import BUFFER_UNMAP
from runtime_selftest.checks import Checks
from suites.memory.borrower import ANSWER, OFFERED
from suites.support import children, raw
from suites.support.expectations import (
    EXITED_CLEANLY,
    LOAD_PAGE_FAULT,
    STORE_PAGE_FAULT,
    error_code,
    faulted,
)
from suites.support.layout import PAGE_BYTES
from suites.support.reporting import Context

BORROWER = "suites.memory.borrower"
BUFFER_BYTES = 2 * PAGE_BYTES
READ_ONLY = RIGHT_READ | RIGHT_MAP
READ_WRITE = READ_ONLY | RIGHT_WRITE
UNKNOWN_RIGHT = 0x80


def borrow(context: Context, role: bytes, buffer: int, rights: int) -> tuple[int, int]:
    return children.run(context.system, BORROWER, role, grants=((buffer, rights),))


def check_limits(checks: Checks, buffer: int) -> None:
    checks.require(
        error_code(memory.create_buffer, 0) == INVALID_ARGUMENT, "an empty buffer is refused"
    )
    checks.require(
        error_code(memory.create_buffer, BUFFER_MAX_BYTES + 1) == LIMIT_EXCEEDED,
        "a buffer above the size limit is refused",
    )
    checks.require(
        raw.map_buffer(buffer, RIGHT_WRITE)[0] == -INVALID_ARGUMENT,
        "a write-only mapping is refused",
    )
    checks.require(
        raw.map_buffer(buffer, RIGHT_READ | UNKNOWN_RIGHT)[0] == -INVALID_ARGUMENT,
        "a mapping with unknown rights is refused",
    )
    checks.require(
        raw.call(BUFFER_UNMAP, PAGE_BYTES) == -INVALID_ARGUMENT,
        "unmapping an address that is not a mapping is refused",
    )


def run(context: Context, checks: Checks) -> None:
    buffer = memory.create_buffer(BUFFER_BYTES)
    mapping = memory.Mapping(buffer, True)
    checks.require(mapping.size == BUFFER_BYTES, "the mapping covers the whole buffer")
    checks.require(
        mapping.read(0, BUFFER_BYTES) == bytes(BUFFER_BYTES), "a new buffer starts zeroed"
    )
    mapping.write(0, OFFERED)

    checks.require(
        borrow(context, b"reader", buffer, READ_ONLY) == EXITED_CLEANLY,
        "a reader sees the content and cannot map it writable",
    )
    checks.require(
        borrow(context, b"vandal", buffer, READ_ONLY) == faulted(STORE_PAGE_FAULT),
        "a store into a read-only mapping stops the process",
    )
    checks.require(mapping.read(0, len(OFFERED)) == OFFERED, "the content survives the vandal")
    checks.require(
        borrow(context, b"stale", buffer, READ_ONLY) == faulted(LOAD_PAGE_FAULT),
        "a load from a removed mapping stops the process",
    )
    checks.require(
        borrow(context, b"writer", buffer, READ_WRITE) == EXITED_CLEANLY,
        "a writer with the write right maps the buffer writable",
    )
    checks.require(mapping.read(0, len(ANSWER)) == ANSWER, "both processes share the same pages")

    check_limits(checks, buffer)
    mapping.unmap()
    capabilities.close(buffer)
