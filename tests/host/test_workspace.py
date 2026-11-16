from pathlib import Path

import pytest

from kernel_tool.cli import main
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.workspace import default_cache_dir, open_workspace


def test_open_workspace_finds_the_root_from_a_nested_directory(tmp_path: Path) -> None:
    (tmp_path / "toolchain.lock.toml").write_text("version = 1\n", encoding="utf-8")
    nested = tmp_path / "native" / "arch"
    nested.mkdir(parents=True)

    workspace = open_workspace(nested, None, {"KERNEL_TOOL_CACHE": str(tmp_path / "cache")})

    assert workspace.root == tmp_path.resolve()
    assert workspace.build_dir == tmp_path.resolve() / "build"
    assert workspace.cache_dir == tmp_path.resolve() / "cache"


def test_open_workspace_fails_outside_a_repository(tmp_path: Path) -> None:
    with pytest.raises(CheckError, match=r"toolchain\.lock\.toml not found"):
        open_workspace(tmp_path, None, {})


def test_cache_directory_follows_xdg_when_no_override_is_set(tmp_path: Path) -> None:
    assert default_cache_dir({"XDG_CACHE_HOME": str(tmp_path)}) == tmp_path / "kernel-tool"


def test_command_outside_a_repository_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["toolchain"]) == ExitCode.FAILED
