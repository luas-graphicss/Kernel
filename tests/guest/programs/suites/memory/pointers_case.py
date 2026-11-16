import _probe

from kernel_client import capabilities, ipc, memory
from kernel_protocol.errors.codes import (
    BAD_ADDRESS,
    INVALID_ARGUMENT,
    MESSAGE_TOO_LARGE,
    UNSUPPORTED,
)
from kernel_protocol.identity.rights import RIGHT_READ
from kernel_protocol.processes.status import COUNTERS
from kernel_protocol.syscalls.numbers import (
    BUFFER_MAP,
    BUFFER_UNMAP,
    COUNT,
    DEADLINE_NEVER,
    DEBUG_WRITE,
    DEBUG_WRITE_MAX_BYTES,
    IPC_RECEIVE,
    IPC_SEND,
    PROCESS_SPAWN,
    SYSTEM_COUNTERS,
)
from kernel_protocol.wire.message import HEADER_BYTES, Message
from runtime_selftest.checks import Checks
from suites.support import raw
from suites.support.layout import (
    BUFFER_WINDOW,
    CONSOLE_REGISTERS,
    NULL_PAGE,
    PAGE_BYTES,
    SUPERVISOR_IMAGE,
    SUPERVISOR_MEMORY,
    WORD_BYTES,
    Layout,
)
from suites.support.reporting import Context

REJECTED = -BAD_ADDRESS
ADDRESS_SPACE_END = 0xFFFFFFFFFFFFFFFC
STORAGE_BYTES = 64
METADATA_BYTES = 32
COUNTERS_BYTES = COUNTERS * WORD_BYTES
UNKNOWN_CALLS = (COUNT, 4096, 1 << 62, -1)
KEPT_PAYLOAD = b"kept"


def check_reads(checks: Checks, layout: Layout) -> None:
    sources = (
        ("the null page", NULL_PAGE),
        ("the supervisor image", SUPERVISOR_IMAGE),
        ("device registers", CONSOLE_REGISTERS),
        ("a range that crosses into the guard page", layout.heap_end - WORD_BYTES // 2),
        ("a range that wraps the address space", ADDRESS_SPACE_END),
        ("an unmapped page of the user region", layout.above_stack()),
    )
    for description, address in sources:
        checks.require(
            raw.call(DEBUG_WRITE, address, WORD_BYTES) == REJECTED,
            f"a read from {description} is refused",
        )
    checks.require(
        raw.call(DEBUG_WRITE, layout.read_only, DEBUG_WRITE_MAX_BYTES + 1) == -MESSAGE_TOO_LARGE,
        "an oversized debug write is refused before it is read",
    )


def check_writes(context: Context, checks: Checks, layout: Layout) -> None:
    destinations = (
        ("the null page", NULL_PAGE),
        ("supervisor memory", SUPERVISOR_MEMORY),
        ("read-only data", layout.read_only),
        ("program text", layout.text),
        ("a range that crosses into the guard page", layout.heap_end - WORD_BYTES),
    )
    for description, address in destinations:
        checks.require(
            raw.call(SYSTEM_COUNTERS, context.system, address, COUNTERS_BYTES) == REJECTED,
            f"a write to {description} is refused",
        )
    storage = bytearray(COUNTERS_BYTES)
    checks.require(
        raw.call(SYSTEM_COUNTERS, context.system, _probe.address(storage), COUNTERS_BYTES - 1)
        == -INVALID_ARGUMENT,
        "a counters buffer that is too short is refused",
    )


def check_messages(context: Context, checks: Checks, layout: Layout) -> None:
    endpoint = ipc.create_endpoint()
    storage = bytearray(STORAGE_BYTES)
    metadata = bytearray(METADATA_BYTES)
    ipc.send(endpoint, Message(1, 0, 7, KEPT_PAYLOAD))
    checks.require(
        raw.call(
            IPC_RECEIVE,
            endpoint,
            NULL_PAGE,
            STORAGE_BYTES,
            _probe.address(metadata),
            DEADLINE_NEVER,
        )
        == REJECTED,
        "receive refuses an invalid message buffer",
    )
    checks.require(
        raw.call(
            IPC_RECEIVE,
            endpoint,
            _probe.address(storage),
            STORAGE_BYTES,
            layout.read_only,
            DEADLINE_NEVER,
        )
        == REJECTED,
        "receive refuses read-only metadata",
    )
    checks.require(
        ipc.receive(endpoint).message.payload == KEPT_PAYLOAD,
        "a refused receive leaves the message queued",
    )
    checks.require(
        raw.call(IPC_SEND, endpoint, SUPERVISOR_IMAGE, HEADER_BYTES, 0, DEADLINE_NEVER) == REJECTED,
        "send refuses a message in supervisor memory",
    )
    checks.require(
        raw.call(PROCESS_SPAWN, context.system, NULL_PAGE) == REJECTED,
        "spawn refuses an invalid request",
    )
    capabilities.close(endpoint)


def check_mapping_description(checks: Checks, layout: Layout) -> None:
    buffer = memory.create_buffer(PAGE_BYTES)
    checks.require(
        raw.call(BUFFER_MAP, buffer, RIGHT_READ, layout.read_only) == REJECTED,
        "map refuses a read-only description",
    )
    status, address, _length = raw.map_buffer(buffer, RIGHT_READ)
    checks.require(
        status == 0 and address == BUFFER_WINDOW, "a refused map leaves no mapping behind"
    )
    checks.require(raw.call(BUFFER_UNMAP, address) == 0, "the mapping is removed on request")
    capabilities.close(buffer)


def run(context: Context, checks: Checks) -> None:
    layout = Layout()
    check_reads(checks, layout)
    check_writes(context, checks, layout)
    check_messages(context, checks, layout)
    check_mapping_description(checks, layout)
    for number in UNKNOWN_CALLS:
        checks.require(raw.call(number) == -UNSUPPORTED, "an unknown system call is refused")
