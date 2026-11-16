from kernel_client import capabilities, ipc
from kernel_protocol.identity.rights import RIGHT_SEND
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.raw import read_word
from suites.support.reporting import Context

KEEPER = "suites.memory.keeper"
SEEDS = (17, 90)


def run(context: Context, checks: Checks) -> None:
    reports = ipc.create_endpoint()
    grants = ((reports, RIGHT_SEND),)
    keepers = [
        children.start(context.system, KEEPER, bytes(str(seed), "ascii"), grants=grants)
        for seed in SEEDS
    ]
    addresses = [read_word(ipc.receive(reports).message.payload, 0) for _ in SEEDS]
    checks.require(addresses[0] == addresses[1], "both processes use the same virtual address")
    for keeper in keepers:
        checks.require(
            children.finish(keeper) == EXITED_CLEANLY, "each process keeps its own content"
        )
    capabilities.close(reports)
