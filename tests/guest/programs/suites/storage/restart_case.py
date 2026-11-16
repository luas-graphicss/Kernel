from kernel_client import services
from kernel_client.blocks import BlockDevice
from kernel_protocol.errors.codes import BAD_STATE, INVALID_HANDLE
from kernel_protocol.services.block import OPERATION_READ as BLOCK_READ
from kernel_protocol.services.block import encode_transfer
from kernel_protocol.services.files import (
    OPEN_READ,
    OPERATION_READ,
    encode_extent,
    encode_request,
)
from kernel_services.init.manifest import DATA_DEVICE
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.platform import enter, load, store
from suites.support.reporting import Context

KEPT = b"data/kept-across-block-restart.txt"
NOTE = b"written before the block service restarted"
BUFFER_BYTES = 4096
REQUEST_TIMEOUT_NANOSECONDS = 5000000000
SUPERBLOCK_MAGIC = b"KVOLSUPR"
SECTORS_PER_BLOCK = 8


def read_first_block(endpoint: int) -> tuple[int, bytes]:
    device = BlockDevice(endpoint, BUFFER_BYTES, REQUEST_TIMEOUT_NANOSECONDS)
    device.read(0, SECTORS_PER_BLOCK)
    start = device.mapping.read(0, len(SUPERBLOCK_MAGIC))
    instance = device.geometry.instance
    device.close()
    return instance, start


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    namespace = enter(system)
    store(namespace, KEPT, NOTE)
    opened = namespace.open(KEPT, OPEN_READ)
    stale_handle = encode_request(namespace.instance, opened.handle, encode_extent(0, 4))
    old_instance, _start = read_first_block(system.blocks[DATA_DEVICE].endpoint)
    checks.require(
        system.restart_block(DATA_DEVICE),
        "the supervisor restarts the block service and the file service that used it",
    )
    new_block = system.blocks[DATA_DEVICE].endpoint
    checks.require(
        error_code(services.call, new_block, BLOCK_READ, encode_transfer(0, 1, 0)) == BAD_STATE,
        "a restarted block service knows no buffer of the instance before it",
    )
    new_instance, start = read_first_block(new_block)
    checks.require(
        new_instance != old_instance and start == SUPERBLOCK_MAGIC,
        "the new instance names itself apart and serves the same device",
    )
    checks.require(
        error_code(services.call, system.filesystem.endpoint, OPERATION_READ, stale_handle)
        == INVALID_HANDLE,
        "the file service started over it refuses the handles of the one before",
    )
    fresh = enter(system)
    checks.require(load(fresh, KEPT) == NOTE, "the volume holds what was written before")
    fresh.remove(KEPT)
    fresh.leave()
