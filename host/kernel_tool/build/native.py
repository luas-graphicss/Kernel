import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.profiles.model import Profile
from kernel_tool.toolchain.resolve import Toolchain
from kernel_tool.workspace import Workspace

BUILD_GOAL = "all"
ANALYSIS_GOAL = "analyze"
LINK_MAP_SUFFIX = ".map"


@dataclass(frozen=True, slots=True)
class BuildOutputs:
    directory: Path
    kernel: Path
    selftest_kernel: Path
    init_program: Path
    init_image: Path
    fault_image: Path
    tests_program: Path
    tests_image: Path

    @property
    def artifacts(self) -> tuple[Path, ...]:
        return (
            self.kernel,
            self.selftest_kernel,
            self.init_image,
            self.fault_image,
            self.tests_image,
        )

    @property
    def executables(self) -> tuple[Path, ...]:
        return (self.kernel, self.selftest_kernel, self.init_program, self.tests_program)

    @property
    def user_programs(self) -> tuple[Path, ...]:
        return (self.init_program, self.tests_program)

    @property
    def user_images(self) -> tuple[Path, ...]:
        return (self.init_image, self.fault_image, self.tests_image)


def link_map(executable: Path) -> Path:
    return executable.with_name(executable.name + LINK_MAP_SUFFIX)


def build_outputs(
    workspace: Workspace, profile: Profile, directory: Path | None = None
) -> BuildOutputs:
    root = directory or workspace.build_dir / profile.name
    return BuildOutputs(
        directory=root,
        kernel=root / "kernel.elf",
        selftest_kernel=root / "kernel-selftest.elf",
        init_program=root / "user" / "init.elf",
        init_image=root / "init.img",
        fault_image=root / "fault.img",
        tests_program=root / "user" / "tests.elf",
        tests_image=root / "tests.img",
    )


def make_variables(profile: Profile, toolchain: Toolchain, directory: Path) -> dict[str, str]:
    layout = profile.layout
    limits = profile.limits
    return {
        "BUILD": str(directory),
        "CROSS_COMPILE": str(toolchain.cross_prefix),
        "MICROPYTHON_DIR": str(toolchain.runtime_source),
        "KERNEL_BASE": hex(layout.kernel_base),
        "SUPERVISOR_STACK_BYTES": hex(layout.supervisor_stack_bytes),
        "EMERGENCY_STACK_BYTES": hex(layout.emergency_stack_bytes),
        "SUPERVISOR_HEAP_BYTES": hex(limits.supervisor_heap_bytes),
        "USER_REGION_BASE": hex(layout.user_region_base),
        "USER_REGION_BYTES": hex(layout.user_region_bytes),
        "USER_HEAP_BYTES": hex(layout.user_heap_bytes),
        "USER_STACK_BYTES": hex(layout.user_stack_bytes),
        "PROFILE_MEMORY_BYTES": str(limits.memory_bytes),
        "PROFILE_PROCESSES": str(limits.processes),
        "PROFILE_PROCESS_HEAP_BYTES": str(limits.process_heap_bytes),
        "PROFILE_CAPABILITIES_PER_PROCESS": str(limits.capabilities_per_process),
        "PROFILE_IPC_PENDING_BYTES_PER_PROCESS": str(limits.ipc_pending_bytes_per_process),
        "PROFILE_IPC_PENDING_BYTES_GLOBAL": str(limits.ipc_pending_bytes_global),
    }


def reproducible_environment(toolchain: Toolchain) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "LC_ALL": "C",
        "TZ": "UTC",
        "SOURCE_DATE_EPOCH": str(toolchain.lock.source_date_epoch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def run_make(
    workspace: Workspace,
    profile: Profile,
    toolchain: Toolchain,
    goal: str,
    directory: Path | None = None,
) -> None:
    make = shutil.which("make")
    if make is None:
        raise InfrastructureError("required host tool 'make' is not installed")

    outputs = build_outputs(workspace, profile, directory)
    variables = make_variables(profile, toolchain, outputs.directory)
    command = [
        make,
        "--no-print-directory",
        "-C",
        str(workspace.root),
        f"-j{os.cpu_count() or 1}",
        goal,
        *(f"{name}={value}" for name, value in variables.items()),
    ]
    completed = subprocess.run(
        command,
        env=reproducible_environment(toolchain),
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,
        check=False,
    )
    if completed.returncode != 0:
        raise CheckError(f"make {goal} exited with status {completed.returncode}")


def build_image(
    workspace: Workspace, profile: Profile, toolchain: Toolchain, directory: Path | None = None
) -> BuildOutputs:
    run_make(workspace, profile, toolchain, BUILD_GOAL, directory)
    outputs = build_outputs(workspace, profile, directory)
    require_artifacts(outputs)
    return outputs


def require_artifacts(outputs: BuildOutputs) -> None:
    for artifact in (*outputs.artifacts, *outputs.user_programs):
        if not artifact.is_file():
            raise CheckError(f"{artifact} does not exist; run kernel-tool build first")
