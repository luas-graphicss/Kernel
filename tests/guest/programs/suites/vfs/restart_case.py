from kernel_client import services
from kernel_protocol.errors.codes import INVALID_HANDLE, NOT_FOUND
from kernel_protocol.services.files import (
    OPEN_READ,
    OPERATION_READ,
    OPERATION_STAT,
    encode_extent,
    encode_request,
)
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.platform import enter, load, store
from suites.support.reporting import Context

VOLATILE = b"tmp/volatile.txt"
KEPT = b"data/kept.txt"
NOTE = b"written before the restart"


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    namespace = enter(system)
    store(namespace, VOLATILE, NOTE)
    store(namespace, KEPT, NOTE)
    opened = namespace.open(KEPT, OPEN_READ)
    stale_session = encode_request(namespace.instance, namespace.session, b"tmp")
    stale_handle = encode_request(namespace.instance, opened.handle, encode_extent(0, 4))
    checks.require(system.restart_filesystem(), "the supervisor restarts the file service")
    endpoint = system.filesystem.endpoint
    checks.require(
        error_code(services.call, endpoint, OPERATION_STAT, stale_session) == INVALID_HANDLE
        and error_code(services.call, endpoint, OPERATION_READ, stale_handle) == INVALID_HANDLE,
        "a restarted service refuses the sessions and handles of the instance before it",
    )
    fresh = enter(system)
    checks.require(
        fresh.instance != namespace.instance, "every instance of the service names itself apart"
    )
    checks.require(
        error_code(fresh.stat, VOLATILE) == NOT_FOUND,
        "temporary files do not outlive the instance that held them",
    )
    checks.require(
        load(fresh, KEPT) == NOTE, "files of the volume outlive a restart of the service"
    )
    fresh.remove(KEPT)
    fresh.leave()
