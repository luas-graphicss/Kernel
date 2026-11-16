import _probe

from kernel_client import memory
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import ACCESS_DENIED
from kernel_protocol.identity.rights import RIGHT_READ
from kernel_protocol.syscalls.numbers import BUFFER_UNMAP
from suites.support import raw
from suites.support.expectations import error_code

OFFERED = b"borrowed"
ANSWER = b"returned"


def read_shared(buffer: int) -> bool:
    mapping = memory.Mapping(buffer, False)
    return (
        mapping.read(0, len(OFFERED)) == OFFERED
        and error_code(memory.Mapping, buffer, True) == ACCESS_DENIED
    )


def store_into_read_only(buffer: int) -> bool:
    _status, address, _length = raw.map_buffer(buffer, RIGHT_READ)
    _probe.store(address, 0)
    return True


def load_after_unmap(buffer: int) -> bool:
    _status, address, _length = raw.map_buffer(buffer, RIGHT_READ)
    raw.call(BUFFER_UNMAP, address)
    _probe.load(address)
    return True


def write_shared(buffer: int) -> bool:
    memory.Mapping(buffer, True).write(0, ANSWER)
    return True


ROLES = {
    b"reader": read_shared,
    b"vandal": store_into_read_only,
    b"stale": load_after_unmap,
    b"writer": write_shared,
}


def main() -> bool:
    startup = Startup()
    return ROLES[startup.argument](startup.handles[0])
