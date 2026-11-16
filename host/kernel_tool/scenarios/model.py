from dataclasses import dataclass
from enum import StrEnum

from kernel_tool.network.orders import Order
from kernel_tool.network.plan import NetworkPlan
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
    SESSION = "session"


class DataSource(StrEnum):
    FORMATTED = "formatted"
    BLANK = "blank"
    KEPT = "kept"
    UNKNOWN_VERSION = "unknown-format-version"
    DAMAGED_NEWEST_ROOT = "newest-root-damaged"


class DataAttachment(StrEnum):
    PLAIN = "plain"
    READ_ONLY = "read-only"
    FLUSH_FAILING = "flush-failing"
    TRACED = "traced"


class DataCheck(StrEnum):
    CONSISTENT = "consistent"
    REPORTED = "reported"
    UNCHANGED = "unchanged"
    UNCHECKED = "unchecked"


@dataclass(frozen=True, slots=True)
class DataDisk:
    source: DataSource = DataSource.FORMATTED
    attachment: DataAttachment = DataAttachment.PLAIN
    check: DataCheck = DataCheck.CONSISTENT


@dataclass(frozen=True, slots=True)
class Devices:
    boot: bool = False
    data: DataDisk | None = None
    scratch: bool = False
    stalled: bool = False
    entropy: bool = False


NO_DEVICES = Devices()
SYSTEM_DEVICES = Devices(boot=True, data=DataDisk(), entropy=True)


@dataclass(frozen=True, slots=True)
class BootEntry:
    path: str
    source: str | None


@dataclass(frozen=True, slots=True)
class Step:
    awaited: str
    typed: str = ""
    orders: tuple[Order, ...] = ()


@dataclass(frozen=True, slots=True)
class Reported:
    event: str
    fields: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class Network:
    plan: NetworkPlan
    reported: tuple[Reported, ...] = ()


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
    devices: Devices = NO_DEVICES
    serial_input: str = ""
    steps: tuple[Step, ...] = ()
    network: Network | None = None
    boot_overlay: tuple[BootEntry, ...] = ()
