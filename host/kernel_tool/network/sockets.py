import os
import tempfile
from pathlib import Path

from kernel_tool.outcome import InfrastructureError

STATION_SOCKET = "station.sock"
GUEST_SOCKET = "guest.sock"
DIRECTORY_PREFIX = "kernel-link-"
SOCKET_ADDRESS_BYTES = 107


def socket_directory() -> tempfile.TemporaryDirectory[str]:
    try:
        directory = tempfile.TemporaryDirectory(prefix=DIRECTORY_PREFIX)
    except OSError as error:
        raise InfrastructureError(
            f"cannot create a directory for the link sockets: {error}"
        ) from error
    longest = max(
        len(os.fsencode(Path(directory.name) / name)) for name in (STATION_SOCKET, GUEST_SOCKET)
    )
    if longest > SOCKET_ADDRESS_BYTES:
        directory.cleanup()
        raise InfrastructureError(
            f"{directory.name} is too deep for the link sockets: a socket path there takes "
            f"{longest} bytes and an address holds {SOCKET_ADDRESS_BYTES}; "
            "point TMPDIR at a shorter directory"
        )
    return directory
