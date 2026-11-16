from kernel_client.processes import clock
from kernel_protocol.services.control import (
    SERVICE_BLOCKED,
    SERVICE_DEGRADED,
    SERVICE_READY,
    SYSTEM_DEGRADED,
)
from kernel_services.manager.processes import Launcher
from kernel_services.manager.supervision import Supervisor
from runtime_selftest.checks import Checks
from suites.supervision.protocol import MUTE
from suites.supervision.units import Sequence, WorkerUnit, policy
from suites.support.reporting import Context


def states(supervisor: Supervisor) -> dict[str, int]:
    return {status.name: status.state for status in supervisor.statuses()}


def run(context: Context, checks: Checks) -> None:
    launcher = Launcher(context.system, context.identity)
    sequence = Sequence()
    silent = WorkerUnit("silent", launcher, sequence, (), MUTE)
    client = WorkerUnit("client", launcher, sequence, (silent,))
    bystander = WorkerUnit("bystander", launcher, sequence)
    supervisor = Supervisor()
    supervisor.add(bystander, policy("bystander", (), 1))
    supervisor.add(silent, policy("silent", (), 2))
    supervisor.add(client, policy("client", ("silent",), 1))
    supervisor.arrange(("bystander", "silent", "client"))
    checks.require(
        not supervisor.start_all(clock()), "a set with a service that never answers is not healthy"
    )
    found = states(supervisor)
    checks.require(
        found["silent"] == SERVICE_DEGRADED,
        "a service that never announces itself is degraded after its restart budget",
    )
    checks.require(
        found["client"] == SERVICE_BLOCKED and sequence.started == ["bystander"],
        "a service is never started while a service it needs is not ready",
    )
    checks.require(
        found["bystander"] == SERVICE_READY and bystander.count() == 1,
        "services that do not need the degraded one keep running",
    )
    failures = [status.failures for status in supervisor.statuses() if status.name == "silent"]
    checks.require(
        failures == [2] and supervisor.state() == SYSTEM_DEGRADED,
        "the degraded state and the spent budget are visible",
    )
    supervisor.check(clock())
    checks.require(
        states(supervisor)["silent"] == SERVICE_DEGRADED and sequence.started == ["bystander"],
        "a degraded service is not started again by itself",
    )
    checks.require(supervisor.stop_all(), "the running services stop in order")
