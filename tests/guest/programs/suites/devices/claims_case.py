from kernel_client import capabilities, devices
from kernel_drivers.virtio_block.driver import VIRTIO_MODEL as BLOCK_MODEL
from kernel_protocol.devices.layout import (
    DEVICE_KIND_SERIAL,
    DEVICE_SERIAL_SLOT,
    DEVICE_SLOTS,
    DEVICE_STATE_CLOSED,
)
from kernel_protocol.errors.codes import ACCESS_DENIED, BAD_STATE, INVALID_ARGUMENT, INVALID_HANDLE
from kernel_protocol.identity.rights import OBJECT_DEVICE, RIGHT_ADMIN, RIGHT_READ
from runtime_selftest.checks import Checks
from suites.devices.access import DEVICE_RIGHTS, slot_of
from suites.support.expectations import error_code
from suites.support.reporting import Context

EMPTY_SLOT = 1
NEVER_ISSUED_HANDLE = 0x7F000001


def check_listing(context: Context, checks: Checks) -> int:
    listed = devices.list_devices(context.system)
    block = slot_of(context, BLOCK_MODEL)
    checks.require(
        listed[0].slot == DEVICE_SERIAL_SLOT and listed[0].kind == DEVICE_KIND_SERIAL,
        "the serial port is the first device",
    )
    checks.require(
        all(device.slot < DEVICE_SLOTS for device in listed),
        "every listed device names a slot of the table",
    )
    checks.require(
        all(device.state == DEVICE_STATE_CLOSED for device in listed if device.slot == block),
        "a transport nobody opened is closed",
    )
    return block


def check_authority(context: Context, checks: Checks, block: int) -> None:
    reader = capabilities.derive(context.system, RIGHT_READ)
    administrator = capabilities.derive(context.system, RIGHT_ADMIN)
    checks.require(
        error_code(devices.claim, reader, block) == ACCESS_DENIED,
        "claiming a device needs the admin right over the system",
    )
    checks.require(
        error_code(devices.list_devices, administrator) == ACCESS_DENIED,
        "listing devices needs the read right over the system",
    )
    checks.require(
        error_code(devices.list_devices, NEVER_ISSUED_HANDLE) == INVALID_HANDLE,
        "a forged handle lists nothing",
    )
    checks.require(
        error_code(devices.claim, context.system, DEVICE_SLOTS) == INVALID_ARGUMENT
        and error_code(devices.claim, context.system, EMPTY_SLOT) == INVALID_ARGUMENT,
        "a slot outside the table or without a device is not claimed",
    )
    capabilities.close(reader)
    capabilities.close(administrator)


def run(context: Context, checks: Checks) -> None:
    block = check_listing(context, checks)
    check_authority(context, checks, block)
    device = devices.claim(context.system, block)
    checks.require(
        capabilities.inspect(device) == (OBJECT_DEVICE, DEVICE_RIGHTS, 0),
        "a claim returns the root capability of the device",
    )
    checks.require(
        error_code(devices.claim, context.system, block) == BAD_STATE,
        "a claimed device is not claimed again",
    )
    capabilities.close(device)
    device = devices.claim(context.system, block)
    checks.require(device != 0, "a released device can be claimed again")
    capabilities.close(device)
