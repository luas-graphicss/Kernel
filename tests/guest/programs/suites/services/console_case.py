from kernel_client import console, services
from kernel_protocol.errors.codes import INVALID_ARGUMENT, MESSAGE_TOO_LARGE, TIMED_OUT
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.console import (
    MAX_WRITE_BYTES,
    OPERATION_READ_LINE,
    OPERATION_WRITE,
    decode_count,
)
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.reporting import Context

WRITTEN = b"console: written by a client\n"
LINE_READER = "suites.services.line_reader"
INPUT_TIMEOUT_NANOSECONDS = 5000000000
SHORT_TIMEOUT_NANOSECONDS = 20000000
SETTLING_NANOSECONDS = 50000000


def check_output(checks: Checks, endpoint: int) -> None:
    accepted, _transferred = services.call(endpoint, OPERATION_WRITE, WRITTEN)
    checks.require(
        decode_count(accepted) == len(WRITTEN), "the console accepts a line and says how much"
    )
    checks.require(
        error_code(services.call, endpoint, OPERATION_WRITE, bytes(MAX_WRITE_BYTES + 1))
        == MESSAGE_TOO_LARGE,
        "a write larger than the console takes at once is refused",
    )


def check_input(checks: Checks, endpoint: int) -> None:
    first = console.read_line(endpoint, INPUT_TIMEOUT_NANOSECONDS)
    second = console.read_line(endpoint, INPUT_TIMEOUT_NANOSECONDS)
    checks.require(
        first == b"first line" and second == b"second line",
        "lines typed on the serial port arrive whole and edited",
    )
    checks.require(
        error_code(console.read_line, endpoint, SHORT_TIMEOUT_NANOSECONDS) == TIMED_OUT,
        "a read without input ends at its deadline",
    )
    checks.require(
        error_code(services.call, endpoint, OPERATION_READ_LINE, b"short") == INVALID_ARGUMENT,
        "a read that states no deadline field is refused",
    )


def check_takeover(checks: Checks, context: Context, endpoint: int) -> None:
    reader = children.start(context.system, LINE_READER, grants=((endpoint, RIGHT_SEND),))
    context.pause(SETTLING_NANOSECONDS)
    checks.require(
        error_code(console.read_line, endpoint, SHORT_TIMEOUT_NANOSECONDS) == TIMED_OUT,
        "the newest reader takes the console over",
    )
    checks.require(
        children.finish(reader) == EXITED_CLEANLY,
        "the reader that lost the console is told its read was cancelled",
    )


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    endpoint = system.console.endpoint
    check_output(checks, endpoint)
    check_input(checks, endpoint)
    check_takeover(checks, context, endpoint)
