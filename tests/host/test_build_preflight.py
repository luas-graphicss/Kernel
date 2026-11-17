from pathlib import Path

import pytest

from kernel_tool.build.native import BUILD_GOAL, run_make
from kernel_tool.build.preflight import require_host_compilers, require_paths_without_whitespace
from kernel_tool.outcome import InfrastructureError
from kernel_tool.profiles.loader import DEFAULT_PROFILE, load_profile
from kernel_tool.toolchain.lock import load_lock
from kernel_tool.toolchain.resolve import Toolchain
from kernel_tool.workspace import Workspace

REPOSITORY = Path(__file__).resolve().parents[2]
EXECUTABLE = 0o755


def install(directory: Path, *tools: str) -> None:
    for tool in tools:
        program = directory / tool
        program.write_text("#!/bin/sh\n", encoding="utf-8")
        program.chmod(EXECUTABLE)


@pytest.mark.parametrize(
    ("role", "root", "build", "cache"),
    [
        ("repository", "/home/user/My Kernel", "/tmp/build", "/tmp/cache"),
        ("build directory", "/home/user/kernel", "/tmp/build dir", "/tmp/cache"),
        ("toolchain cache", "/home/user/kernel", "/tmp/build", "/tmp/cache\tdir"),
    ],
)
def test_a_path_with_whitespace_is_refused_and_named(
    role: str, root: str, build: str, cache: str
) -> None:
    workspace = Workspace(root=Path(root), build_dir=Path(build), cache_dir=Path(cache))
    offending = next(path for path in (root, build, cache) if any(map(str.isspace, path)))

    with pytest.raises(InfrastructureError) as refusal:
        require_paths_without_whitespace(workspace, Path(build))

    assert f"the {role} {offending!r}" in str(refusal.value)


def test_paths_with_accents_and_without_whitespace_are_accepted() -> None:
    workspace = Workspace(
        root=Path("/home/user/Área/kernel"),
        build_dir=Path("/home/user/Área/kernel/build"),
        cache_dir=Path("/home/user/.cache/kernel-tool"),
    )

    require_paths_without_whitespace(workspace, workspace.build_dir / DEFAULT_PROFILE)


def test_make_is_not_started_for_a_build_directory_with_whitespace(tmp_path: Path) -> None:
    lock = load_lock(REPOSITORY / "toolchain.lock.toml")
    toolchain = Toolchain(
        lock=lock, roots={artifact.name: tmp_path / artifact.root for artifact in lock.artifacts}
    )
    workspace = Workspace(
        root=tmp_path / "kernel", build_dir=tmp_path / "build dir", cache_dir=tmp_path / "cache"
    )

    with pytest.raises(InfrastructureError, match="build directory"):
        run_make(workspace, load_profile(REPOSITORY, DEFAULT_PROFILE), toolchain, BUILD_GOAL)

    assert not workspace.build_dir.exists()


@pytest.mark.parametrize(("present", "missing"), [("cc", "gcc"), ("gcc", "cc")])
def test_a_host_without_one_of_the_compiler_names_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, present: str, missing: str
) -> None:
    install(tmp_path, present)
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(InfrastructureError, match=f"host tool '{missing}' is not installed"):
        require_host_compilers()


def test_a_host_with_both_compiler_names_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(tmp_path, "cc", "gcc")
    monkeypatch.setenv("PATH", str(tmp_path))

    require_host_compilers()
