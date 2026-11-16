import subprocess
from pathlib import Path

from kernel_tool.build.native import BuildOutputs
from kernel_tool.images.device_tree import (
    DeviceTree,
    node_paths,
    parse,
    serialize,
    with_property,
    without_node,
)
from kernel_tool.images.user_image import read_header, with_load_base
from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.profiles.model import Profile
from kernel_tool.qemu.command import device_tree_dump_command
from kernel_tool.scenarios.model import BootModule, DeviceTreeSource
from kernel_tool.toolchain.resolve import Toolchain

DUMP_TIMEOUT_SECONDS = 60
PADDED_NODE = "/chosen"
PADDING_PROPERTY = "kernel-tool,padding"
PADDING_BYTES = 0x11000
MEMORY_NODE_PREFIX = "/memory@"
MISPLACED_BYTES = 0x1000


def boot_module_file(kind: BootModule, outputs: BuildOutputs, directory: Path) -> Path | None:
    match kind:
        case BootModule.NONE:
            return None
        case BootModule.INIT:
            return outputs.init_image
        case BootModule.FAULT:
            return outputs.fault_image
        case BootModule.MISPLACED_SEGMENT:
            image = outputs.init_image.read_bytes()
            misplaced = directory / "misplaced-segment.img"
            misplaced.write_bytes(
                with_load_base(image, read_header(image).load_base + MISPLACED_BYTES)
            )
            return misplaced


def edited_device_tree(kind: DeviceTreeSource, generated: bytes) -> bytes:
    tree = parse(generated)
    match kind:
        case DeviceTreeSource.GENERATED:
            return generated
        case DeviceTreeSource.OVERSIZED:
            return serialize(
                with_property(tree, PADDED_NODE, PADDING_PROPERTY, bytes(PADDING_BYTES))
            )
        case DeviceTreeSource.WITHOUT_MEMORY:
            return serialize(without_node(tree, _memory_node(tree)))


def dump_device_tree(
    profile: Profile, toolchain: Toolchain, memory_mib: int, directory: Path
) -> bytes:
    output = directory / f"generated-{memory_mib}m.dtb"
    command = device_tree_dump_command(profile, toolchain, memory_mib, output)
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=DUMP_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InfrastructureError(f"cannot dump the device tree of the machine: {error}") from error
    if completed.returncode != 0 or not output.is_file():
        raise InfrastructureError(
            f"the emulator did not dump its device tree: {completed.stderr.strip()}"
        )
    return output.read_bytes()


def _memory_node(tree: DeviceTree) -> str:
    for path in node_paths(tree):
        if path.startswith(MEMORY_NODE_PREFIX):
            return path
    raise CheckError("the device tree of the machine has no memory node")
