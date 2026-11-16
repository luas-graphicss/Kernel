from kernel_client import capabilities, memory
from kernel_drivers.virtio_block.driver import BlockDriver
from kernel_protocol.errors.codes import IO_ERROR, UNKNOWN_OUTCOME
from runtime_selftest.checks import Checks
from suites.device_reset.requests import STALLED_IDENTITY, STALLED_SECTORS
from suites.devices.access import claim_block, nothing_in_flight
from suites.support.expectations import error_code
from suites.support.layout import PAGE_BYTES
from suites.support.reporting import Context

SHORT_TIMEOUT_NANOSECONDS = 100000000


def run(context: Context, checks: Checks) -> None:
    device = claim_block(context)
    driver = BlockDriver(device, SHORT_TIMEOUT_NANOSECONDS)
    buffer = memory.create_buffer(PAGE_BYTES)
    checks.require(
        driver.sectors == STALLED_SECTORS and driver.identity() == STALLED_IDENTITY,
        "the device answers what needs no storage",
    )
    checks.require(
        error_code(driver.read, 0, 1, buffer, 0) == IO_ERROR,
        "a read the device does not answer in time fails for certain",
    )
    checks.require(
        driver.resets() == 1 and not driver.has_failed() and nothing_in_flight(context),
        "the driver resets the device and nothing stays in flight",
    )
    checks.require(
        error_code(driver.write, 0, 1, buffer, 0) == UNKNOWN_OUTCOME,
        "a write the device does not confirm has an unknown outcome",
    )
    checks.require(
        driver.resets() == 2 and nothing_in_flight(context),
        "every request without an answer costs one reset",
    )
    checks.require(
        driver.identity() == STALLED_IDENTITY, "the session opened after the resets still works"
    )
    driver.close()
    capabilities.close(buffer)
    capabilities.close(device)
