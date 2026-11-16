from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.outcome import CheckError

LOCK_FILE_NAME = "toolchain.lock.toml"
CACHE_VARIABLE = "KERNEL_TOOL_CACHE"


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path
    build_dir: Path
    cache_dir: Path

    @property
    def lock_file(self) -> Path:
        return self.root / LOCK_FILE_NAME


def locate_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / LOCK_FILE_NAME).is_file():
            return candidate
    raise CheckError(f"{LOCK_FILE_NAME} not found in {start} or any parent directory")


def default_cache_dir(environment: Mapping[str, str]) -> Path:
    override = environment.get(CACHE_VARIABLE)
    if override:
        return Path(override)
    xdg_cache = environment.get("XDG_CACHE_HOME")
    base = Path(xdg_cache) if xdg_cache else Path.home() / ".cache"
    return base / "kernel-tool"


def open_workspace(
    start: Path, build_dir: Path | None, environment: Mapping[str, str]
) -> Workspace:
    root = locate_root(start.resolve())
    return Workspace(
        root=root,
        build_dir=(build_dir or root / "build").resolve(),
        cache_dir=default_cache_dir(environment).resolve(),
    )
