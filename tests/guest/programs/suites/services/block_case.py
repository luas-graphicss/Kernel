from kernel_client import capabilities, ipc, services
from kernel_client.blocks import BlockDevice
from kernel_protocol.errors.codes import BAD_STATE, INVALID_ARGUMENT
from kernel_protocol.services.block import (
    FLAG_FLUSH,
    OPERATION_ATTACH,
    OPERATION_READ,
    SECTOR_BYTES,
    encode_transfer,
)
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.reporting import Context

SCRATCH = b"kernel-scratch"
SCRATCH_SECTORS = 2048
BUFFER_BYTES = 8192
BUFFER_SECTORS = BUFFER_BYTES // SECTOR_BYTES
SECOND_PAGE = 4096
FIRST_SECTOR = 16
PATTERN = bytes(range(256)) * 8
PATTERN_SECTORS = len(PATTERN) // SECTOR_BYTES
REQUEST_TIMEOUT_NANOSECONDS = 5000000000
ONE_SECTOR = encode_transfer(0, 1, 0)


def check_transfers(checks: Checks, device: BlockDevice) -> None:
    device.mapping.write(0, PATTERN)
    device.write(FIRST_SECTOR, PATTERN_SECTORS)
    device.flush()
    device.mapping.write(0, bytes(len(PATTERN)))
    device.read(FIRST_SECTOR, PATTERN_SECTORS)
    checks.require(
        device.mapping.read(0, len(PATTERN)) == PATTERN,
        "sectors written through the service read back the same",
    )
    device.read(FIRST_SECTOR + 1, 1, SECOND_PAGE)
    checks.require(
        device.mapping.read(SECOND_PAGE, SECTOR_BYTES) == PATTERN[SECTOR_BYTES : 2 * SECTOR_BYTES],
        "a transfer lands at the offset of the buffer the request names",
    )
    device.read(0, 0)
    device.write(0, 0)
    checks.require(
        device.mapping.read(0, len(PATTERN)) == PATTERN, "a transfer of zero sectors moves nothing"
    )


def check_limits(checks: Checks, device: BlockDevice) -> None:
    sectors = device.geometry.sectors
    checks.require(
        error_code(device.read, sectors, 1) == INVALID_ARGUMENT
        and error_code(device.write, sectors - 1, 2) == INVALID_ARGUMENT,
        "a transfer past the end of the device is refused",
    )
    checks.require(
        error_code(device.read, 0, BUFFER_SECTORS + 1) == INVALID_ARGUMENT
        and error_code(device.read, 0, 1, BUFFER_BYTES) == INVALID_ARGUMENT,
        "a transfer that does not fit in the attached buffer is refused",
    )


def check_attachment(checks: Checks, endpoint: int) -> None:
    spare = ipc.create_endpoint()
    checks.require(
        error_code(services.call, endpoint, OPERATION_ATTACH, b"", spare) == INVALID_ARGUMENT
        and error_code(services.call, endpoint, OPERATION_ATTACH) == INVALID_ARGUMENT,
        "a client attaches a buffer and nothing else",
    )
    capabilities.close(spare)


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    endpoint = system.blocks[SCRATCH].endpoint
    checks.require(
        error_code(services.call, endpoint, OPERATION_READ, ONE_SECTOR) == BAD_STATE,
        "a client attaches a buffer before it asks for sectors",
    )
    check_attachment(checks, endpoint)
    device = BlockDevice(endpoint, BUFFER_BYTES, REQUEST_TIMEOUT_NANOSECONDS)
    checks.require(
        device.geometry.sectors == SCRATCH_SECTORS
        and device.geometry.flags == FLAG_FLUSH
        and device.geometry.identity == SCRATCH,
        "the service describes the device it drives",
    )
    check_transfers(checks, device)
    check_limits(checks, device)
    device.close()
    checks.require(
        error_code(services.call, endpoint, OPERATION_READ, ONE_SECTOR) == BAD_STATE,
        "a detached client has no buffer left in the service",
    )
