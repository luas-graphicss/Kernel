import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from kernel_tool.outcome import InfrastructureError
from kernel_tool.toolchain.fetch import sha256_file
from kernel_tool.toolchain.resolve import Toolchain

VERSION_TIMEOUT_SECONDS = 20
PINNED_CROSS_TOOLS = ("gcc", "ld", "objcopy")
EMULATOR_TOOL = "qemu-system-riscv64"
HOST_TOOLS = ("make", "cc")


@dataclass(frozen=True, slots=True)
class PinnedRecord:
    name: str
    version: str
    sha256: str
    license: str


@dataclass(frozen=True, slots=True)
class ToolRecord:
    name: str
    origin: str
    version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Inventory:
    host: str
    source_date_epoch: int
    artifacts: tuple[PinnedRecord, ...]
    components: tuple[PinnedRecord, ...]
    tools: tuple[ToolRecord, ...]

    def to_document(self) -> dict[str, object]:
        return asdict(self)


def collect_inventory(toolchain: Toolchain) -> Inventory:
    lock = toolchain.lock
    pinned_tools = [
        _describe(f"riscv-none-elf-{name}", "pinned", toolchain.cross_tool(name))
        for name in PINNED_CROSS_TOOLS
    ]
    pinned_tools.append(_describe(EMULATOR_TOOL, "pinned", toolchain.emulator(EMULATOR_TOOL)))
    host_tools = [_describe(name, "host", _locate_host_tool(name)) for name in HOST_TOOLS]
    python = ToolRecord(
        name="python",
        origin="host",
        version=sys.version.split()[0],
        sha256=sha256_file(Path(sys.executable).resolve()),
    )
    return Inventory(
        host=lock.host,
        source_date_epoch=lock.source_date_epoch,
        artifacts=tuple(
            PinnedRecord(artifact.name, artifact.version, artifact.sha256, artifact.license)
            for artifact in lock.artifacts
        ),
        components=tuple(
            PinnedRecord(component.name, component.version, component.sha256, component.license)
            for component in lock.components
        ),
        tools=(*pinned_tools, *host_tools, python),
    )


def _locate_host_tool(name: str) -> Path:
    location = shutil.which(name)
    if location is None:
        raise InfrastructureError(f"required host tool {name!r} is not installed")
    return Path(location).resolve()


def _describe(name: str, origin: str, executable: Path) -> ToolRecord:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_SECONDS,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise InfrastructureError(f"{executable} --version failed: {error}") from error
    version = completed.stdout.splitlines()[0].strip()
    return ToolRecord(name=name, origin=origin, version=version, sha256=sha256_file(executable))
