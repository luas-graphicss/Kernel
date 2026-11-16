import _process
from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    UNSUPPORTED,
)
from kernel_protocol.identity.rights import RIGHT_ADMIN, RIGHT_READ, RIGHT_RECEIVE, RIGHT_SEND
from kernel_protocol.processes.status import ARGUMENT_BYTES, COUNTERS, GRANTS
from kernel_protocol.wire.spawn import encode_spawn_request
from runtime_selftest.checks import Checks
from suites.support.children import CHILD_HEAP_BYTES
from suites.support.expectations import error_code
from suites.support.reporting import Context

SLEEPER = "suites.support.sleeper"
PRIORITY = processes.DEFAULT_PRIORITY
MORE_URGENT_PRIORITY = 0
NO_HANDLE = 0
NEVER_ISSUED_HANDLE = 0x7F000001
VERSION_OFFSET = 0
PRIORITY_OFFSET = 4
NAME_LENGTH_OFFSET = 24
ARGUMENT_LENGTH_OFFSET = 28
GRANT_COUNT_OFFSET = 32
RESERVED_OFFSET = 36
UNUSED_GRANT_OFFSET = 40
NAME_OFFSET = 168
MALFORMED_REQUESTS = (
    ("an unknown version", VERSION_OFFSET, 2, UNSUPPORTED),
    ("a priority outside the levels", PRIORITY_OFFSET, 4, INVALID_ARGUMENT),
    ("an empty program name", NAME_LENGTH_OFFSET, 0, INVALID_ARGUMENT),
    ("an oversized argument", ARGUMENT_LENGTH_OFFSET, ARGUMENT_BYTES + 1, INVALID_ARGUMENT),
    ("too many grants", GRANT_COUNT_OFFSET, GRANTS + 1, INVALID_ARGUMENT),
    ("a reserved field in use", RESERVED_OFFSET, 1, INVALID_ARGUMENT),
    ("an unused grant that is not zero", UNUSED_GRANT_OFFSET, 1, INVALID_ARGUMENT),
    ("a program name outside the alphabet", NAME_OFFSET, ord("S"), INVALID_ARGUMENT),
    ("bytes after the program name", NAME_OFFSET + len(SLEEPER), ord("x"), INVALID_ARGUMENT),
)


def spawn_error(authority: int, priority: int = PRIORITY, grants=()) -> int:
    return error_code(
        processes.spawn, authority, SLEEPER, b"", priority, CHILD_HEAP_BYTES, 0, grants
    )


def check_authority(context: Context, checks: Checks, endpoint: int) -> None:
    checks.require(
        spawn_error(endpoint) == INVALID_HANDLE, "an endpoint is not the system capability"
    )
    checks.require(spawn_error(NO_HANDLE) == INVALID_HANDLE, "the null handle names nothing")
    observer = capabilities.derive(context.system, RIGHT_READ)
    operator = capabilities.derive(context.system, RIGHT_ADMIN)
    checks.require(spawn_error(observer) == ACCESS_DENIED, "spawn needs the admin right")
    checks.require(
        len(system.counters(observer)) == COUNTERS, "the read right is enough for counters"
    )
    checks.require(
        error_code(system.counters, operator) == ACCESS_DENIED, "counters need the read right"
    )
    checks.require(
        spawn_error(context.system, MORE_URGENT_PRIORITY) == ACCESS_DENIED,
        "a process cannot start a more urgent process",
    )
    capabilities.close(observer)
    capabilities.close(operator)


def check_grants(context: Context, checks: Checks, endpoint: int) -> None:
    sender = capabilities.derive(endpoint, RIGHT_SEND)
    refused = (
        ("a handle that was never issued", NEVER_ISSUED_HANDLE, RIGHT_SEND, INVALID_HANDLE),
        ("a right the capability lacks", endpoint, RIGHT_READ, ACCESS_DENIED),
        ("the receive right", endpoint, RIGHT_RECEIVE, ACCESS_DENIED),
        ("a capability without the delegate right", sender, RIGHT_SEND, ACCESS_DENIED),
    )
    for description, handle, rights, code in refused:
        checks.require(
            spawn_error(context.system, grants=((handle, rights),)) == code,
            f"a grant of {description} is refused",
        )
    capabilities.close(sender)


def check_malformed_requests(context: Context, checks: Checks) -> None:
    valid = encode_spawn_request(SLEEPER, b"", PRIORITY, CHILD_HEAP_BYTES, 0, ())
    for description, offset, value, code in MALFORMED_REQUESTS:
        request = bytearray(valid)
        request[offset] = value
        checks.require(
            _process.spawn(context.system, request) == -code,
            f"a request with {description} is refused",
        )


def run(context: Context, checks: Checks) -> None:
    endpoint = ipc.create_endpoint()
    check_authority(context, checks, endpoint)
    check_grants(context, checks, endpoint)
    check_malformed_requests(context, checks)
    capabilities.close(endpoint)
