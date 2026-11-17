from pathlib import Path

from kernel_tool.outcome import InfrastructureError
from kernel_tool.toolchain.host_tools import locate_host_tool
from kernel_tool.workspace import Workspace

HOST_COMPILERS = ("cc", "gcc")


def require_paths_without_whitespace(workspace: Workspace, build_directory: Path) -> None:
    locations = (
        ("repository", workspace.root),
        ("build directory", build_directory),
        ("toolchain cache", workspace.cache_dir),
    )
    for role, path in locations:
        if any(character.isspace() for character in str(path)):
            raise InfrastructureError(
                f"the {role} {str(path)!r} has whitespace in its path, and make splits "
                "file names at whitespace; use a path without spaces"
            )


def require_host_compilers() -> None:
    for name in HOST_COMPILERS:
        locate_host_tool(name)
