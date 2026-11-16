from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.identity.rights import RIGHT_ADMIN, RIGHT_READ, RIGHT_SEND, RIGHT_WRITE

REGISTRATION = "registration"
DEVICE = "device"
BLOCKS = "blocks"
KNOWN_GRANTS = {
    REGISTRATION: RIGHT_SEND,
    DEVICE: RIGHT_READ | RIGHT_WRITE | RIGHT_ADMIN,
    BLOCKS: RIGHT_SEND,
}

BOOT_DEVICE = b"kernel-boot"
DATA_DEVICE = b"kernel-data"
BOOT_MOUNT = b"boot"
DATA_MOUNT = b"data"
STORAGE = ((BOOT_MOUNT, BOOT_DEVICE), (DATA_MOUNT, DATA_DEVICE))
MAX_BLOCK_DEVICES = 4


class Service:
    def __init__(
        self, program: str, priority: int, heap_bytes: int, grants: tuple[str, ...]
    ) -> None:
        for grant in grants:
            if grant not in KNOWN_GRANTS:
                raise KernelError(INVALID_ARGUMENT, "service asks for an unknown capability")
        self.program = program
        self.priority = priority
        self.heap_bytes = heap_bytes
        self.grants = grants


SERVICES = (Service("kernel_services.echo.main", 2, 0x40000, (REGISTRATION,)),)

CONSOLE = Service("kernel_services.console.main", 1, 0x40000, (REGISTRATION, DEVICE))
ENTROPY = Service("kernel_services.entropy.main", 2, 0x40000, (REGISTRATION, DEVICE))
BLOCK = Service("kernel_services.block.main", 1, 0x40000, (REGISTRATION, DEVICE))
FILESYSTEM = Service("kernel_services.filesystem.main", 2, 0x200000, (REGISTRATION, BLOCKS))
SYSTEM_SERVICES = (CONSOLE, ENTROPY, BLOCK, FILESYSTEM)
