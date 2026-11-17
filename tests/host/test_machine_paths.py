from pathlib import Path

from kernel_tool.build.native import BuildOutputs
from kernel_tool.toolchain.lock import load_lock
from kernel_tool.toolchain.resolve import Toolchain
from kernel_tool.verification.machine_paths import (
    machine_directories,
    machine_path_problems,
    named_directories,
)

REPOSITORY = Path(__file__).resolve().parents[2]
HEADER = b"lib/gcc/riscv-none-elf/15.2.0/include/stdint.h"


def toolchain_below(cache: Path) -> Toolchain:
    lock = load_lock(REPOSITORY / "toolchain.lock.toml")
    return Toolchain(
        lock=lock, roots={artifact.name: cache / artifact.root for artifact in lock.artifacts}
    )


def built_outputs(directory: Path, kernel: bytes) -> BuildOutputs:
    outputs = BuildOutputs(
        directory=directory,
        kernel=directory / "kernel.elf",
        selftest_kernel=directory / "kernel-selftest.elf",
        init_program=directory / "user" / "init.elf",
        init_image=directory / "init.img",
        fault_image=directory / "fault.img",
        tests_program=directory / "user" / "tests.elf",
        tests_image=directory / "tests.img",
        boot_image=directory / "boot.img",
    )
    (directory / "user").mkdir(parents=True)
    for path in (*outputs.artifacts, *outputs.user_programs):
        path.write_bytes(b"\x7fELF native/include/kernel/memory.h\0")
    outputs.kernel.write_bytes(kernel)
    return outputs


def test_the_workspace_the_build_and_the_toolchain_are_the_machine_directories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "kernel"
    (root / "native").mkdir(parents=True)
    (root / "toolchain.lock.toml").write_text("", encoding="utf-8")
    toolchain = toolchain_below(tmp_path / "cache")
    outputs = built_outputs(tmp_path / "elsewhere", b"")

    directories = machine_directories(root, outputs, toolchain)

    assert root / "native" in directories
    assert root / "toolchain.lock.toml" not in directories
    assert outputs.directory in directories
    assert toolchain.compiler_root in directories
    assert toolchain.runtime_source in directories


def test_a_relative_path_that_ends_like_the_workspace_is_not_a_machine_directory() -> None:
    image = b"\0native/include/kernel/memory.h\0kernel_core/bootstrap.py\0"

    assert named_directories(image, (Path("/kernel/native"), Path("/kernel/src"))) == []


def test_an_image_that_names_the_compiler_directory_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "kernel"
    root.mkdir()
    toolchain = toolchain_below(tmp_path / "cache")
    leaked = b"\x7fELF\0" + bytes(toolchain.compiler_root) + b"/" + HEADER + b"\0"
    outputs = built_outputs(root / "build", leaked)

    problems = machine_path_problems(root, outputs, toolchain)

    assert problems == [f"kernel.elf: names the build machine directory {toolchain.compiler_root}"]


def test_images_with_mapped_paths_have_no_problem(tmp_path: Path) -> None:
    root = tmp_path / "kernel"
    root.mkdir()
    toolchain = toolchain_below(tmp_path / "cache")
    outputs = built_outputs(root / "build", b"\x7fELF\0compiler/" + HEADER + b"\0build/genhdr\0")

    assert machine_path_problems(root, outputs, toolchain) == []
