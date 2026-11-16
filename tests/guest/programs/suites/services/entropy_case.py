from kernel_client import entropy, services
from kernel_protocol.errors.codes import INVALID_ARGUMENT, UNSUPPORTED
from kernel_protocol.services.entropy import MAX_READ_BYTES, OPERATION_READ, encode_count
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.reporting import Context

SAMPLE_BYTES = 32
LARGE_BYTES = 600
UNKNOWN_OPERATION = 99


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    endpoint = system.entropy.endpoint
    first = entropy.read(endpoint, SAMPLE_BYTES)
    second = entropy.read(endpoint, SAMPLE_BYTES)
    checks.require(
        len(first) == SAMPLE_BYTES and len(second) == SAMPLE_BYTES and first != second,
        "the service returns the bytes asked for and two samples differ",
    )
    checks.require(
        len(entropy.read(endpoint, LARGE_BYTES)) == LARGE_BYTES,
        "a request larger than one transfer is served in parts",
    )
    checks.require(
        error_code(services.call, endpoint, OPERATION_READ, encode_count(0)) == INVALID_ARGUMENT
        and error_code(services.call, endpoint, OPERATION_READ, encode_count(MAX_READ_BYTES + 1))
        == INVALID_ARGUMENT
        and error_code(services.call, endpoint, OPERATION_READ, b"") == INVALID_ARGUMENT,
        "a request for nothing, for too much or without a count is refused",
    )
    checks.require(
        error_code(services.call, endpoint, UNKNOWN_OPERATION) == UNSUPPORTED,
        "an operation outside the service is refused",
    )
