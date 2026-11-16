from dataclasses import dataclass
from enum import StrEnum

from kernel_tool.verification.transcript import KernelStatus


class Image(StrEnum):
    KERNEL = "kernel"
    SELFTEST = "selftest"


class BootModule(StrEnum):
    NONE = "none"
    INIT = "init"
    FAULT = "fault"
    TESTS = "tests"
    MISPLACED_SEGMENT = "misplaced-segment"


class DeviceTreeSource(StrEnum):
    GENERATED = "generated"
    OVERSIZED = "oversized"
    WITHOUT_MEMORY = "without-memory"


class Deadline(StrEnum):
    BOOT = "boot"
    SELFTEST = "selftest"
    SOAK = "soak"


@dataclass(frozen=True, slots=True, kw_only=True)
class Scenario:
    name: str
    image: Image
    boot_module: BootModule
    expected_status: KernelStatus
    expected_lines: tuple[str, ...]
    forbidden_lines: tuple[str, ...] = ()
    device_tree: DeviceTreeSource = DeviceTreeSource.GENERATED
    memory_mib: int | None = None
    arguments: str | None = None
    repeats: int = 1
    deadline: Deadline = Deadline.BOOT
    compares_corpus: bool = False
