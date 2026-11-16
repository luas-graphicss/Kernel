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


@dataclass(frozen=True, slots=True)
class BuildOutputs:
    directory: Path
    kernel: Path
    link_map: Path


def build_outputs(workspace: Workspace, profile: Profile) -> BuildOutputs:
    directory = workspace.build_dir / profile.name
    kernel = directory / "kernel.elf"
    return BuildOutputs(directory=directory, kernel=kernel, link_map=Path(f"{kernel}.map"))


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
        "PROFILE_MEMORY_BYTES": str(limits.memory_bytes),
    }


def reproducible_environment(toolchain: Toolchain) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "LC_ALL": "C",
        "TZ": "UTC",
        "SOURCE_DATE_EPOCH": str(toolchain.lock.source_date_epoch),
    }


def run_make(workspace: Workspace, profile: Profile, toolchain: Toolchain, goal: str) -> None:
    make = shutil.which("make")
    if make is None:
        raise InfrastructureError("required host tool 'make' is not installed")

    outputs = build_outputs(workspace, profile)
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


def build_image(workspace: Workspace, profile: Profile, toolchain: Toolchain) -> BuildOutputs:
    run_make(workspace, profile, toolchain, BUILD_GOAL)
    outputs = build_outputs(workspace, profile)
    if not outputs.kernel.is_file():
        raise CheckError(f"the build did not produce {outputs.kernel}")
    return outputs
