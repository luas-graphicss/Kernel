from kernel_client import capabilities, entropy, ipc, services
from kernel_protocol.errors.codes import INVALID_ARGUMENT
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.entropy import OPERATION_READ, encode_count
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.reporting import Context

INTRUDER = "suites.services.intruder"
SCRATCH = b"kernel-scratch"
SAMPLE_BYTES = 8


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    endpoints = (
        system.console.endpoint,
        system.entropy.endpoint,
        system.blocks[SCRATCH].endpoint,
        system.filesystem.endpoint,
    )
    grants = tuple((endpoint, RIGHT_SEND) for endpoint in endpoints)
    checks.require(
        children.run(context.system, INTRUDER, grants=grants) == EXITED_CLEANLY,
        "a process that is not the supervisor stops no service and takes no root",
    )
    spare = ipc.create_endpoint()
    request = encode_count(SAMPLE_BYTES)
    checks.require(
        error_code(services.call, system.entropy.endpoint, OPERATION_READ, request, spare)
        == INVALID_ARGUMENT,
        "a capability sent with a request that takes none is refused and dropped",
    )
    capabilities.close(spare)
    checks.require(
        len(entropy.read(system.entropy.endpoint, SAMPLE_BYTES)) == SAMPLE_BYTES,
        "the services answer after the refusals",
    )
