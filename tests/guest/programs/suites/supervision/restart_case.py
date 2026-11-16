from kernel_client import capabilities, services
from kernel_client.processes import clock
from kernel_protocol.errors.codes import PEER_CLOSED
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.control import (
    SERVICE_BLOCKED,
    SERVICE_DEGRADED,
    SERVICE_READY,
    SYSTEM_DEGRADED,
    SYSTEM_RUNNING,
)
from kernel_services.manager.processes import Launcher
from kernel_services.manager.supervision import Supervisor
from runtime_selftest.checks import Checks
from suites.supervision.protocol import OPERATION_COUNT
from suites.supervision.units import SECOND, Sequence, WorkerUnit, policy
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.reporting import Context

CALLER = "suites.supervision.caller"
SHORT_WINDOW = SECOND // 2


def build(context: Context, restarts: int, window: int):
    launcher = Launcher(context.system, context.identity)
    sequence = Sequence()
    base = WorkerUnit("base", launcher, sequence)
    client = WorkerUnit("client", launcher, sequence, (base,))
    bystander = WorkerUnit("bystander", launcher, sequence)
    supervisor = Supervisor()
    supervisor.add(base, policy("base", (), restarts, window))
    supervisor.add(client, policy("client", ("base",), 1))
    supervisor.add(bystander, policy("bystander", (), 1))
    supervisor.arrange(("base", "bystander", "client"))
    return supervisor, sequence, base, client, bystander


def states(supervisor: Supervisor) -> dict[str, int]:
    return {status.name: status.state for status in supervisor.statuses()}


def run_restart(context: Context, checks: Checks) -> None:
    supervisor, sequence, base, client, bystander = build(context, 2, 60 * SECOND)
    checks.require(supervisor.start_all(clock()), "the set starts")
    checks.require(base.count() == 1 and base.count() == 2, "the service counts its requests")
    stale = capabilities.derive(base.endpoint(), RIGHT_SEND)
    handles = client.handles()
    waiting = children.start(context.system, CALLER, grants=((base.endpoint(), RIGHT_SEND),))
    context.pause(SECOND // 10)
    base.crash()
    supervisor.check(clock())
    checks.require(
        children.finish(waiting) == EXITED_CLEANLY,
        "a request that was pending when the service died ends with an error",
    )
    checks.require(
        supervisor.state() == SYSTEM_RUNNING
        and sequence.started == ["base", "bystander", "client", "base", "client"],
        "the dead service is restarted and then the services that need it",
    )
    checks.require(
        error_code(services.call, stale, OPERATION_COUNT) == PEER_CLOSED,
        "the endpoint of the dead instance is closed for whoever still holds it",
    )
    capabilities.close(stale)
    checks.require(
        base.count() == 1, "the new instance starts over instead of repeating old effects"
    )
    checks.require(
        client.handles() == handles and bystander.count() == 1,
        "the restarted client holds no more authority and the bystander never stopped",
    )
    checks.require(supervisor.stop_all(), "the set stops")


def run_budget(context: Context, checks: Checks) -> None:
    supervisor, sequence, base, _client, bystander = build(context, 2, 60 * SECOND)
    checks.require(supervisor.start_all(clock()), "the set starts")
    for _ in range(2):
        base.crash()
        supervisor.check(clock())
    checks.require(
        states(supervisor)["base"] == SERVICE_READY, "two failures stay inside a budget of two"
    )
    base.crash()
    supervisor.check(clock())
    found = states(supervisor)
    checks.require(
        found["base"] == SERVICE_DEGRADED and found["client"] == SERVICE_BLOCKED,
        "the failure beyond the budget degrades the service and blocks what needs it",
    )
    starts = len(sequence.started)
    supervisor.check(clock())
    supervisor.check(clock())
    checks.require(
        len(sequence.started) == starts and supervisor.state() == SYSTEM_DEGRADED,
        "a degraded service is not restarted in a loop",
    )
    checks.require(
        found["bystander"] == SERVICE_READY and bystander.count() == 1,
        "a service outside the failure keeps answering",
    )
    checks.require(supervisor.stop_all(), "what still runs stops in order")


def run_window(context: Context, checks: Checks) -> None:
    supervisor, _sequence, base, _client, _bystander = build(context, 1, SHORT_WINDOW)
    checks.require(supervisor.start_all(clock()), "the set starts")
    base.crash()
    supervisor.check(clock())
    checks.require(states(supervisor)["base"] == SERVICE_READY, "one failure fits the budget")
    context.pause(2 * SHORT_WINDOW)
    base.crash()
    supervisor.check(clock())
    checks.require(
        states(supervisor)["base"] == SERVICE_READY and supervisor.state() == SYSTEM_RUNNING,
        "a failure older than the window no longer counts against the budget",
    )
    base.crash()
    supervisor.check(clock())
    checks.require(
        states(supervisor)["base"] == SERVICE_DEGRADED,
        "a second failure inside the window spends the budget",
    )
    checks.require(supervisor.stop_all(), "what still runs stops in order")
