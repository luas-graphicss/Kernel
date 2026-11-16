from pathlib import Path

from kernel_tool.profiles.loader import DEFAULT_PROFILE, load_profile
from kernel_tool.qemu.command import BootRequest, boot_command, device_tree_dump_command
from kernel_tool.toolchain.lock import load_lock
from kernel_tool.toolchain.resolve import Toolchain

REPOSITORY = Path(__file__).resolve().parents[2]
TOOLS = Path("/tools")


def reference_toolchain() -> Toolchain:
    lock = load_lock(REPOSITORY / "toolchain.lock.toml")
    return Toolchain(
        lock=lock, roots={artifact.name: TOOLS / artifact.root for artifact in lock.artifacts}
    )


def option_value(command: list[str], option: str) -> str:
    return command[command.index(option) + 1]


def test_boot_command_pins_the_reference_machine() -> None:
    profile = load_profile(REPOSITORY, DEFAULT_PROFILE)
    request = BootRequest(kernel=Path("/build/kernel.elf"), memory_mib=256)

    command = boot_command(profile, reference_toolchain(), request)

    assert command[0] == "/tools/xpack-qemu-riscv-9.2.4-1/bin/qemu-system-riscv64"
    assert option_value(command, "-machine") == "virt,aia=none,acpi=off"
    assert option_value(command, "-cpu") == "rv64,h=off,v=off"
    assert option_value(command, "-smp") == "1"
    assert option_value(command, "-m") == "256M"
    assert option_value(command, "-accel") == "tcg"
    assert option_value(command, "-global") == "virtio-mmio.force-legacy=false"
    assert option_value(command, "-kernel") == "/build/kernel.elf"
    assert option_value(command, "-bios").endswith(
        "share/qemu/opensbi-riscv64-generic-fw_dynamic.bin"
    )
    assert "-nodefaults" in command
    assert "-no-reboot" in command
    assert "-initrd" not in command
    assert "-dtb" not in command
    assert "-append" not in command


def test_boot_command_adds_optional_boot_inputs() -> None:
    profile = load_profile(REPOSITORY, DEFAULT_PROFILE)
    request = BootRequest(
        kernel=Path("/build/kernel.elf"),
        memory_mib=128,
        boot_module=Path("/build/user.img"),
        device_tree=Path("/build/patched.dtb"),
        arguments="selftest=supervisor-trap",
    )

    command = boot_command(profile, reference_toolchain(), request)

    assert option_value(command, "-m") == "128M"
    assert option_value(command, "-initrd") == "/build/user.img"
    assert option_value(command, "-dtb") == "/build/patched.dtb"
    assert option_value(command, "-append") == "selftest=supervisor-trap"


def test_boot_never_enables_semihosting() -> None:
    profile = load_profile(REPOSITORY, DEFAULT_PROFILE)
    request = BootRequest(
        kernel=Path("/build/kernel.elf"),
        memory_mib=256,
        boot_module=Path("/build/init.img"),
        arguments="probe=supervisor-trap",
    )

    command = boot_command(profile, reference_toolchain(), request)

    assert not any("semihosting" in argument for argument in command)


def test_device_tree_dump_uses_the_reference_machine_without_booting() -> None:
    profile = load_profile(REPOSITORY, DEFAULT_PROFILE)

    command = device_tree_dump_command(
        profile, reference_toolchain(), 128, Path("/build/a,b/generated.dtb")
    )

    assert (
        option_value(command, "-machine")
        == "virt,aia=none,acpi=off,dumpdtb=/build/a,,b/generated.dtb"
    )
    assert option_value(command, "-m") == "128M"
    assert option_value(command, "-cpu") == "rv64,h=off,v=off"
    assert "-kernel" not in command
    assert "-serial" not in command
