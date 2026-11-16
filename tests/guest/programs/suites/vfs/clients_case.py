from kernel_client import capabilities
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.files import NAMESPACE_READ, NAMESPACE_WRITE
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.platform import enter, load, names, remove_tree
from suites.support.reporting import Context
from suites.vfs.records import RECORDS, WRITERS, record_of
from suites.vfs.visitor import SHARED_NAME

ROOT = b"data/clients"
VISITOR = "suites.vfs.visitor"


def own_records(slot: int) -> bytes:
    return b"".join([record_of(slot, record) for record in range(RECORDS)])


def shared_records() -> bytes:
    return b"".join(
        [record_of(slot, record) for record in range(RECORDS) for slot in range(WRITERS)]
    )


def run(services: ServiceSystem, context: Context, checks: Checks) -> None:
    namespace = enter(services)
    namespace.make_directory(ROOT)
    identity, capability = namespace.subspace(ROOT, NAMESPACE_READ | NAMESPACE_WRITE)
    grants = ((services.filesystem.endpoint, RIGHT_SEND), (capability, RIGHT_SEND))
    writers = [
        children.start(context.system, VISITOR, bytes(f"writer {slot}", "ascii"), grants=grants)
        for slot in range(WRITERS)
    ]
    seen = names(namespace, ROOT)
    outcomes = [children.finish(writer) for writer in writers]
    checks.require(
        all(outcome == EXITED_CLEANLY for outcome in outcomes),
        "every client finishes its writes while the others run",
    )
    checks.require(
        len(seen) <= WRITERS + 1, "a listing taken during the writes shows only whole entries"
    )
    checks.require(
        load(namespace, ROOT + b"/" + SHARED_NAME) == shared_records(),
        "the writes of several clients to one file all take effect",
    )
    checks.require(
        all(
            load(namespace, ROOT + bytes(f"/writer-{slot}", "ascii")) == own_records(slot)
            for slot in range(WRITERS)
        ),
        "each client finds its own file as it wrote it",
    )
    namespace.drop(identity)
    capabilities.close(capability)
    remove_tree(namespace, ROOT)
    namespace.leave()
