from kernel_client import capabilities, devices, memory, processes
from kernel_drivers.virtio_block.driver import VIRTIO_MODEL as BLOCK_MODEL
from kernel_drivers.virtio_block.driver import BlockDriver
from kernel_protocol.devices.layout import DEVICE_STATE_CLOSED, DEVICE_STATE_FAILED
from kernel_protocol.errors.codes import BAD_STATE
from runtime_selftest.checks import Checks
from suites.device_reset.requests import STALLED_IDENTITY, submit_headerless
from suites.devices.access import claim_block, nothing_in_flight, slot_of
from suites.support.expectations import error_code
from suites.support.layout import PAGE_BYTES
from suites.support.reporting import Context

PATIENCE_NANOSECONDS = 2000000000
REQUEST_TIMEOUT_NANOSECONDS = 2000000000


def state_of(context: Context) -> int:
    slot = slot_of(context, BLOCK_MODEL)
    for device in devices.list_devices(context.system):
        if device.slot == slot:
            return device.state
    return DEVICE_STATE_CLOSED


def run(context: Context, checks: Checks) -> None:
    device = claim_block(context)
    buffer = memory.create_buffer(PAGE_BYTES)
    devices.open_session(device, 0)
    submit_headerless(device, buffer)
    checks.require(
        error_code(devices.wait, device, processes.clock() + PATIENCE_NANOSECONDS) == BAD_STATE,
        "a driver waiting on a device that reports a failure is woken with an error",
    )
    checks.require(
        state_of(context) == DEVICE_STATE_FAILED
        and error_code(submit_headerless, device, buffer) == BAD_STATE,
        "a failed device takes no request until it is reset",
    )
    devices.reset(device)
    checks.require(
        state_of(context) == DEVICE_STATE_CLOSED and nothing_in_flight(context),
        "the reset clears the failure and unpins the request that caused it",
    )
    driver = BlockDriver(device, REQUEST_TIMEOUT_NANOSECONDS)
    checks.require(
        driver.identity() == STALLED_IDENTITY, "the device answers again after the reset"
    )
    driver.close()
    capabilities.close(buffer)
    capabilities.close(device)
