from kernel_client import capabilities, memory
from kernel_drivers.virtio_block.driver import SECTOR_BYTES, BlockDriver
from kernel_protocol.errors.codes import INVALID_ARGUMENT
from runtime_selftest.checks import Checks
from suites.devices.access import REQUEST_TIMEOUT_NANOSECONDS, claim_block, nothing_in_flight
from suites.support.expectations import error_code
from suites.support.layout import PAGE_BYTES
from suites.support.reporting import Context

SCRATCH_IDENTITY = b"kernel-scratch"
SCRATCH_SECTORS = 2048
FIRST_SECTOR = 8
PATTERN = bytes(range(256)) * 4
PATTERN_SECTORS = len(PATTERN) // SECTOR_BYTES
BUFFER_BYTES = 2 * PAGE_BYTES
BUFFER_SECTORS = BUFFER_BYTES // SECTOR_BYTES


def check_geometry(checks: Checks, driver: BlockDriver) -> None:
    checks.require(
        driver.sectors == SCRATCH_SECTORS, "the driver reads the capacity from the device"
    )
    checks.require(
        driver.can_flush and not driver.read_only, "the device offers flush and accepts writes"
    )
    checks.require(driver.identity() == SCRATCH_IDENTITY, "the device names itself")


def check_round_trip(
    checks: Checks, driver: BlockDriver, buffer: int, mapping: memory.Mapping
) -> None:
    mapping.write(0, PATTERN)
    driver.write(FIRST_SECTOR, PATTERN_SECTORS, buffer, 0)
    driver.flush()
    mapping.write(0, bytes(len(PATTERN)))
    driver.read(FIRST_SECTOR, PATTERN_SECTORS, buffer, 0)
    checks.require(mapping.read(0, len(PATTERN)) == PATTERN, "sectors read back what was written")
    driver.read(FIRST_SECTOR + 1, 1, buffer, PAGE_BYTES)
    checks.require(
        mapping.read(PAGE_BYTES, SECTOR_BYTES) == PATTERN[SECTOR_BYTES:],
        "a single sector lands at the offset the request names",
    )
    driver.read(driver.sectors - 1, 1, buffer, PAGE_BYTES)
    checks.require(
        mapping.read(PAGE_BYTES, SECTOR_BYTES) == bytes(SECTOR_BYTES),
        "the last sector of the device is readable",
    )


def check_limits(checks: Checks, driver: BlockDriver, buffer: int, mapping: memory.Mapping) -> None:
    driver.read(0, 0, buffer, 0)
    driver.write(0, 0, buffer, 0)
    checks.require(
        mapping.read(0, len(PATTERN)) == PATTERN, "a transfer of zero sectors moves nothing"
    )
    checks.require(
        error_code(driver.read, driver.sectors, 1, buffer, 0) == INVALID_ARGUMENT
        and error_code(driver.write, driver.sectors - 1, 2, buffer, 0) == INVALID_ARGUMENT,
        "a transfer past the end of the device is refused",
    )
    checks.require(
        error_code(driver.read, 0, BUFFER_SECTORS + 1, buffer, 0) == INVALID_ARGUMENT,
        "a transfer larger than the buffer is refused",
    )


def run(context: Context, checks: Checks) -> None:
    device = claim_block(context)
    driver = BlockDriver(device, REQUEST_TIMEOUT_NANOSECONDS)
    buffer = memory.create_buffer(BUFFER_BYTES)
    mapping = memory.Mapping(buffer, True)
    check_geometry(checks, driver)
    check_round_trip(checks, driver, buffer, mapping)
    check_limits(checks, driver, buffer, mapping)
    driver.close()
    checks.require(nothing_in_flight(context), "a closed driver leaves nothing in flight")
    mapping.unmap()
    capabilities.close(buffer)
    capabilities.close(device)
