from kernel_client import devices
from kernel_drivers.virtio_block.driver import VIRTIO_MODEL as BLOCK_MODEL
from kernel_drivers.virtio_entropy.driver import VIRTIO_MODEL as ENTROPY_MODEL
from kernel_drivers.virtio_network.driver import VIRTIO_MODEL as NETWORK_MODEL
from kernel_protocol.devices.layout import DEVICE_KIND_SERIAL, DEVICE_KIND_VIRTIO
from kernel_protocol.identity.rights import RIGHT_ADMIN, RIGHT_READ, RIGHT_WRITE

NO_DEVICE = 0
MAX_BLOCK_DEVICES = 2
DRIVER_RIGHTS = RIGHT_READ | RIGHT_WRITE | RIGHT_ADMIN


class Inventory:
    def __init__(self) -> None:
        self.serial = NO_DEVICE
        self.entropy = NO_DEVICE
        self.network = NO_DEVICE
        self.blocks: list[int] = []


def discover(system: int) -> Inventory:
    inventory = Inventory()
    for device in devices.list_devices(system):
        if device.kind == DEVICE_KIND_SERIAL:
            if inventory.serial == NO_DEVICE:
                inventory.serial = devices.claim(system, device.slot)
        elif device.kind != DEVICE_KIND_VIRTIO:
            continue
        elif device.model == ENTROPY_MODEL:
            if inventory.entropy == NO_DEVICE:
                inventory.entropy = devices.claim(system, device.slot)
        elif device.model == NETWORK_MODEL:
            if inventory.network == NO_DEVICE:
                inventory.network = devices.claim(system, device.slot)
        elif device.model == BLOCK_MODEL and len(inventory.blocks) < MAX_BLOCK_DEVICES:
            inventory.blocks.append(devices.claim(system, device.slot))
    return inventory
