from dataclasses import dataclass
from pathlib import Path

from kernel_tool.profiles.model import Profile
from kernel_tool.qemu.drives import Drive, drive_arguments
from kernel_tool.toolchain.resolve import Toolchain

ENTROPY_ARGUMENTS = (
    "-object",
    "rng-builtin,id=entropy",
    "-device",
    "virtio-rng-device,rng=entropy",
)


@dataclass(frozen=True, slots=True)
class BootRequest:
    kernel: Path
    memory_mib: int
    boot_module: Path | None = None
    device_tree: Path | None = None
    arguments: str | None = None
    drives: tuple[Drive, ...] = ()
    entropy: bool = False
    network: tuple[str, ...] = ()


def machine_arguments(
    profile: Profile, toolchain: Toolchain, memory_mib: int, machine_options: tuple[str, ...] = ()
) -> list[str]:
    machine = profile.machine
    arguments = [
        str(toolchain.emulator(machine.emulator)),
        "-machine",
        ",".join((machine.machine, *machine_options)),
        "-cpu",
        machine.cpu,
        "-smp",
        str(machine.harts),
        "-m",
        f"{memory_mib}M",
        "-accel",
        machine.accelerator,
        "-nodefaults",
        "-display",
        "none",
        "-monitor",
        "none",
        "-no-reboot",
    ]
    for setting in machine.globals:
        arguments.extend(["-global", setting])
    return arguments


def boot_command(profile: Profile, toolchain: Toolchain, request: BootRequest) -> list[str]:
    command = machine_arguments(profile, toolchain, request.memory_mib)
    command.extend(
        [
            "-serial",
            "stdio",
            "-bios",
            str(toolchain.component_path(profile.machine.firmware)),
            "-kernel",
            str(request.kernel),
        ]
    )
    if request.boot_module is not None:
        command.extend(["-initrd", str(request.boot_module)])
    if request.device_tree is not None:
        command.extend(["-dtb", str(request.device_tree)])
    if request.arguments is not None:
        command.extend(["-append", request.arguments])
    for drive in request.drives:
        command.extend(drive_arguments(drive))
    if request.entropy:
        command.extend(ENTROPY_ARGUMENTS)
    command.extend(request.network)
    return command


def device_tree_dump_command(
    profile: Profile, toolchain: Toolchain, memory_mib: int, output: Path
) -> list[str]:
    escaped_output = str(output).replace(",", ",,")
    command = machine_arguments(profile, toolchain, memory_mib, (f"dumpdtb={escaped_output}",))
    command.extend(["-bios", str(toolchain.component_path(profile.machine.firmware))])
    return command
