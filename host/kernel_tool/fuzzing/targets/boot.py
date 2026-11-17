from kernel_protocol.configuration.errors import ConfigurationError
from kernel_protocol.configuration.validation import Limits, load
from kernel_tool.fuzzing.model import Family, InterpretedTarget, NativeTarget
from kernel_tool.fuzzing.native import DEVICE_TREE_ENTRY, USER_IMAGE_ENTRY
from kernel_tool.fuzzing.targets.device_tree_seed import reference_tree
from kernel_tool.fuzzing.targets.text import guest_text
from kernel_tool.images import user_image

SEED_CONFIGURATION = b"""[system]
version = 1
name = "kernel"

[interface]
address = "10.0.2.15"
prefix = 24
gateway = "10.0.2.2"
mtu = 1500

[service.console]
restarts = 2
window_seconds = 60

[service.entropy]
restarts = 2
window_seconds = 60

[service.storage]
restarts = 2
window_seconds = 60
heap_bytes = 2097152

[service.network]
needs = ["entropy"]
restarts = 3
window_seconds = 60
heap_bytes = 4194304

[service.shell]
needs = ["console", "storage"]
restarts = 3
window_seconds = 60
heap_bytes = 2097152

[access.shell]
network = ["connect", "listen", "datagram", "echo", "inspect"]
files = "read-write"
control = ["observe", "launch", "signal", "power"]

[access.application]
network = ["connect", "listen", "datagram", "echo", "inspect"]
files = "read-write"
limit = 4
heap_bytes = 2097152
"""
PROCESS_LIMIT = 16
MAX_DEVICE_TREE_BYTES = 66560
MAX_USER_IMAGE_BYTES = 16384
MAX_CONFIGURATION_BYTES = 20480
REGION_BASE = 0x4000_0000
FILE_BYTES = 0x2800
ENTRY_OFFSET = 0x80
TEXT_BYTES = 0x1000
RODATA_BYTES = 0x1000
DATA_BYTES = 0x2000
HEAP_BYTES = 0x4000
STACK_BYTES = 0x2000


def device_tree_seeds() -> tuple[bytes, ...]:
    reference = reference_tree()
    return (reference, reference[: len(reference) // 2])


def user_image_seeds() -> tuple[bytes, ...]:
    header = user_image.HEADER.pack(
        user_image.MAGIC,
        user_image.VERSION,
        REGION_BASE,
        FILE_BYTES,
        REGION_BASE + ENTRY_OFFSET,
        TEXT_BYTES,
        RODATA_BYTES,
        DATA_BYTES,
        HEAP_BYTES,
        STACK_BYTES,
    )
    return (header + bytes(FILE_BYTES - len(header)), header)


def configuration_seeds() -> tuple[bytes, ...]:
    return (SEED_CONFIGURATION, b"[system]\nversion = 1\n")


def load_configuration(data: bytes) -> None:
    load(guest_text(data), Limits(PROCESS_LIMIT))


TARGETS = (
    NativeTarget(
        name="device-tree",
        family=Family.BOOT,
        sources=(
            "native/supervisor/devices/device_tree",
            "native/include/kernel/devices/device_tree.h",
            "native/include/kernel/devices/device_inventory.h",
        ),
        max_input_bytes=MAX_DEVICE_TREE_BYTES,
        seeds=device_tree_seeds,
        entry=DEVICE_TREE_ENTRY,
    ),
    NativeTarget(
        name="user-image",
        family=Family.BOOT,
        sources=(
            "native/supervisor/processes/user_image.c",
            "native/include/kernel/processes/user_image.h",
            "native/include/kernel/abi/user_image.h",
        ),
        max_input_bytes=MAX_USER_IMAGE_BYTES,
        seeds=user_image_seeds,
        entry=USER_IMAGE_ENTRY,
    ),
    InterpretedTarget(
        name="configuration",
        family=Family.BOOT,
        sources=("src/kernel_protocol/configuration",),
        max_input_bytes=MAX_CONFIGURATION_BYTES,
        seeds=configuration_seeds,
        run=load_configuration,
        refusals=(ConfigurationError,),
    ),
)
