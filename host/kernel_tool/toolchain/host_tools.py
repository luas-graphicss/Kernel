import shutil
from pathlib import Path

from kernel_tool.outcome import InfrastructureError


def locate_host_tool(name: str) -> Path:
    location = shutil.which(name)
    if location is None:
        raise InfrastructureError(f"required host tool {name!r} is not installed")
    return Path(location)
