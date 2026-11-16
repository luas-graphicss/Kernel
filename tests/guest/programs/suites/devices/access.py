from kernel_client import devices, system
from kernel_drivers.virtio_block.driver import VIRTIO_MODEL as BLOCK_MODEL
from kernel_drivers.virtio_entropy.driver import VIRTIO_MODEL as ENTROPY_MODEL
from kernel_protocol.devices.layout import DEVICE_KIND_VIRTIO, DEVICE_SERIAL_SLOT
from kernel_protocol.errors.codes import NOT_FOUND, KernelError
from kernel_protocol.identity.rights import RIGHT_ADMIN, RIGHT_DELEGATE, RIGHT_READ, RIGHT_WRITE
from kernel_protocol.processes.status import COUNTER_DEVICE_REQUESTS, COUNTER_PINNED_BUFFERS
from suites.support.reporting import Context

DEVICE_RIGHTS = RIGHT_READ | RIGHT_WRITE | RIGHT_ADMIN | RIGHT_DELEGATE
DRIVER_RIGHTS = RIGHT_READ | RIGHT_WRITE | RIGHT_ADMIN
REQUEST_TIMEOUT_NANOSECONDS = 5000000000


def slot_of(context: Context, model: int) -> int:
    for device in devices.list_devices(context.system):
        if device.kind == DEVICE_KIND_VIRTIO and device.model == model:
            return device.slot
    raise KernelError(NOT_FOUND, "the machine has no such device")


def claim_block(context: Context) -> int:
    return devices.claim(context.system, slot_of(context, BLOCK_MODEL))


def claim_entropy(context: Context) -> int:
    return devices.claim(context.system, slot_of(context, ENTROPY_MODEL))


def claim_serial(context: Context) -> int:
    return devices.claim(context.system, DEVICE_SERIAL_SLOT)


def nothing_in_flight(context: Context) -> bool:
    counters = system.counters(context.system)
    return counters[COUNTER_DEVICE_REQUESTS] == 0 and counters[COUNTER_PINNED_BUFFERS] == 0
