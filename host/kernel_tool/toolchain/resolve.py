import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.toolchain.fetch import ensure_artifact, sha256_file
from kernel_tool.toolchain.lock import ToolchainLock

COMPILER_ARTIFACT = "riscv-none-elf-gcc"
EMULATOR_ARTIFACT = "qemu-riscv"
RUNTIME_ARTIFACT = "micropython"
FIRMWARE_COMPONENT = "opensbi"
CROSS_PREFIX = "riscv-none-elf-"


@dataclass(frozen=True, slots=True)
class Toolchain:
    lock: ToolchainLock
    roots: dict[str, Path]

    def cross_tool(self, name: str) -> Path:
        return self.roots[COMPILER_ARTIFACT] / "bin" / f"{CROSS_PREFIX}{name}"

    @property
    def cross_prefix(self) -> Path:
        return self.roots[COMPILER_ARTIFACT] / "bin" / CROSS_PREFIX

    @property
    def runtime_source(self) -> Path:
        return self.roots[RUNTIME_ARTIFACT]

    def emulator(self, name: str) -> Path:
        return self.roots[EMULATOR_ARTIFACT] / "bin" / name

    def component_path(self, name: str) -> Path:
        component = self.lock.component(name)
        return self.roots[component.artifact] / component.path


def current_host() -> str:
    return f"{sys.platform}-{platform.machine()}"


def ensure_toolchain(lock: ToolchainLock, cache_dir: Path) -> Toolchain:
    host = current_host()
    if host != lock.host:
        raise InfrastructureError(f"the pinned toolchain supports {lock.host}; this host is {host}")

    roots = {artifact.name: ensure_artifact(artifact, cache_dir) for artifact in lock.artifacts}
    toolchain = Toolchain(lock=lock, roots=roots)
    for component in lock.components:
        actual = sha256_file(toolchain.component_path(component.name))
        if actual != component.sha256:
            raise CheckError(
                f"{component.name} {component.version}: sha256 {actual} "
                f"does not match the lock ({component.sha256})"
            )
    return toolchain
