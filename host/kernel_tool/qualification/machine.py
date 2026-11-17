import os
import platform
from pathlib import Path

from kernel_tool.profiles.model import Profile
from kernel_tool.toolchain.inventory import EMULATOR_TOOL, collect_inventory
from kernel_tool.toolchain.resolve import Toolchain

PROCESSOR_FILE = Path("/proc/cpuinfo")
PROCESSOR_FIELD = "model name"
MEMORY_FILE = Path("/proc/meminfo")
MEMORY_FIELD = "MemTotal"
UNKNOWN = "unknown"


def reference_machine(profile: Profile, toolchain: Toolchain) -> dict[str, object]:
    inventory = collect_inventory(toolchain)
    emulator = next(tool for tool in inventory.tools if tool.name == EMULATOR_TOOL)
    return {
        "host": platform.platform(),
        "processor": _field(PROCESSOR_FILE, PROCESSOR_FIELD),
        "processors": os.cpu_count() or 0,
        "host_memory": _field(MEMORY_FILE, MEMORY_FIELD),
        "emulator": emulator.version,
        "emulator_sha256": emulator.sha256,
        "accelerator": profile.machine.accelerator,
        "machine": profile.machine.machine,
        "cpu": profile.machine.cpu,
        "harts": profile.machine.harts,
        "guest_memory_mib": profile.machine.memory_mib,
    }


def _field(path: Path, name: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return UNKNOWN
    for line in lines:
        key, _, value = line.partition(":")
        if key.strip() == name:
            return value.strip()
    return UNKNOWN
