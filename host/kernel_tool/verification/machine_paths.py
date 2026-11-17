from pathlib import Path

from kernel_tool.build.native import BuildOutputs
from kernel_tool.toolchain.resolve import Toolchain


def machine_directories(
    root: Path, outputs: BuildOutputs, toolchain: Toolchain
) -> tuple[Path, ...]:
    sources = sorted(child for child in root.iterdir() if child.is_dir())
    return (*sources, outputs.directory, *toolchain.roots.values())


def named_directories(image: bytes, directories: tuple[Path, ...]) -> list[Path]:
    return [directory for directory in directories if bytes(directory) in image]


def machine_path_problems(root: Path, outputs: BuildOutputs, toolchain: Toolchain) -> list[str]:
    directories = machine_directories(root, outputs, toolchain)
    return [
        f"{path.name}: names the build machine directory {directory}"
        for path in (*outputs.artifacts, *outputs.user_programs)
        for directory in named_directories(path.read_bytes(), directories)
    ]
