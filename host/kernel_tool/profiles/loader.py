import re
import tomllib
from pathlib import Path

from kernel_tool.outcome import CheckError
from kernel_tool.profiles.model import Deadlines, Layout, Limits, Machine, Profile

DEFAULT_PROFILE = "qemu-riscv64"
PROFILE_DIRECTORY = Path("config") / "profiles"
PROFILE_NAME_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
BYTES_PER_MIB = 1 << 20


class Section:
    def __init__(self, document: dict[str, object], name: str) -> None:
        table = document.get(name)
        if not isinstance(table, dict):
            raise CheckError(f"profile is missing the [{name}] table")
        self._name = name
        self._table = table
        self._read: set[str] = set()

    def text(self, key: str) -> str:
        value = self._take(key)
        if not isinstance(value, str) or not value:
            raise CheckError(f"[{self._name}] {key} must be a non-empty string")
        return value

    def positive(self, key: str) -> int:
        value = self._take(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise CheckError(f"[{self._name}] {key} must be a positive integer")
        return value

    def texts(self, key: str) -> tuple[str, ...]:
        value = self._take(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise CheckError(f"[{self._name}] {key} must be a list of strings")
        return tuple(value)

    def finish(self) -> None:
        unknown = sorted(set(self._table) - self._read)
        if unknown:
            raise CheckError(f"[{self._name}] has unknown keys: {', '.join(unknown)}")

    def _take(self, key: str) -> object:
        if key not in self._table:
            raise CheckError(f"[{self._name}] is missing {key}")
        self._read.add(key)
        return self._table[key]


def load_profile(root: Path, name: str) -> Profile:
    if not PROFILE_NAME_PATTERN.fullmatch(name):
        raise CheckError(f"invalid profile name {name!r}")
    path = root / PROFILE_DIRECTORY / f"{name}.toml"
    if not path.is_file():
        raise CheckError(f"profile {name!r} does not exist at {path}")
    try:
        with path.open("rb") as source:
            document = tomllib.load(source)
    except tomllib.TOMLDecodeError as error:
        raise CheckError(f"{path}: {error}") from error

    if document.get("name") != name:
        raise CheckError(f"{path}: name must be {name!r}")
    profile = Profile(
        name=name,
        machine=_machine(Section(document, "machine")),
        layout=_layout(Section(document, "layout")),
        limits=_limits(Section(document, "limits")),
        deadlines=_deadlines(Section(document, "deadlines")),
    )
    _check_consistency(profile)
    return profile


def _machine(section: Section) -> Machine:
    machine = Machine(
        emulator=section.text("emulator"),
        machine=section.text("machine"),
        cpu=section.text("cpu"),
        harts=section.positive("harts"),
        memory_mib=section.positive("memory_mib"),
        accelerator=section.text("accelerator"),
        globals=section.texts("globals"),
        firmware=section.text("firmware"),
    )
    section.finish()
    return machine


def _layout(section: Section) -> Layout:
    layout = Layout(
        kernel_base=section.positive("kernel_base"),
        user_region_base=section.positive("user_region_base"),
        user_region_bytes=section.positive("user_region_bytes"),
        supervisor_stack_bytes=section.positive("supervisor_stack_bytes"),
        emergency_stack_bytes=section.positive("emergency_stack_bytes"),
        user_heap_bytes=section.positive("user_heap_bytes"),
        user_stack_bytes=section.positive("user_stack_bytes"),
    )
    section.finish()
    return layout


def _limits(section: Section) -> Limits:
    limits = Limits(
        memory_bytes=section.positive("memory_bytes"),
        processes=section.positive("processes"),
        supervisor_heap_bytes=section.positive("supervisor_heap_bytes"),
        process_heap_bytes=section.positive("process_heap_bytes"),
        capabilities_per_process=section.positive("capabilities_per_process"),
        delegation_depth=section.positive("delegation_depth"),
        ipc_inline_payload_bytes=section.positive("ipc_inline_payload_bytes"),
        endpoint_messages=section.positive("endpoint_messages"),
        ipc_pending_bytes_per_process=section.positive("ipc_pending_bytes_per_process"),
        ipc_pending_bytes_global=section.positive("ipc_pending_bytes_global"),
    )
    section.finish()
    return limits


def _deadlines(section: Section) -> Deadlines:
    deadlines = Deadlines(boot_seconds=section.positive("boot_seconds"))
    section.finish()
    return deadlines


def _check_consistency(profile: Profile) -> None:
    machine_bytes = profile.machine.memory_mib * BYTES_PER_MIB
    if machine_bytes != profile.limits.memory_bytes:
        raise CheckError(
            f"profile {profile.name}: the machine has {machine_bytes} bytes of memory "
            f"but the limits require {profile.limits.memory_bytes}"
        )
    if profile.layout.user_heap_bytes > profile.limits.process_heap_bytes:
        raise CheckError(
            f"profile {profile.name}: the user heap exceeds the heap limit of a process"
        )
