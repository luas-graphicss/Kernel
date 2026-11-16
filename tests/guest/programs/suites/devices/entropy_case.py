from kernel_client import capabilities
from kernel_drivers.virtio_entropy.driver import MAX_BYTES, EntropyDriver
from kernel_protocol.errors.codes import INVALID_ARGUMENT
from runtime_selftest.checks import Checks
from suites.devices.access import REQUEST_TIMEOUT_NANOSECONDS, claim_entropy, nothing_in_flight
from suites.support.expectations import error_code
from suites.support.reporting import Context

SAMPLE_BYTES = 32


def run(context: Context, checks: Checks) -> None:
    device = claim_entropy(context)
    driver = EntropyDriver(device, REQUEST_TIMEOUT_NANOSECONDS)
    first = driver.read(SAMPLE_BYTES)
    second = driver.read(SAMPLE_BYTES)
    checks.require(
        0 < len(first) <= SAMPLE_BYTES and 0 < len(second) <= SAMPLE_BYTES,
        "the device returns at most the bytes that were asked for",
    )
    checks.require(first != second, "two samples differ")
    checks.require(len(driver.read(MAX_BYTES)) > 0, "the largest request is served")
    checks.require(
        error_code(driver.read, 0) == INVALID_ARGUMENT
        and error_code(driver.read, MAX_BYTES + 1) == INVALID_ARGUMENT,
        "a request outside one transfer is refused",
    )
    driver.close()
    checks.require(nothing_in_flight(context), "a closed driver leaves nothing in flight")
    capabilities.close(device)
