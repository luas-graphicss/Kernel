from kernel_client.processes import clock
from kernel_protocol.services.control import SERVICE_READY, SYSTEM_RUNNING
from kernel_services.manager.processes import Launcher
from kernel_services.manager.supervision import Supervisor
from runtime_selftest.checks import Checks
from suites.supervision.units import Sequence, WorkerUnit, policy
from suites.support.reporting import Context


def run(context: Context, checks: Checks) -> None:
    launcher = Launcher(context.system, context.identity)
    sequence = Sequence()
    base = WorkerUnit("base", launcher, sequence)
    middle = WorkerUnit("middle", launcher, sequence, (base,))
    top = WorkerUnit("top", launcher, sequence, (middle, base))
    supervisor = Supervisor()
    supervisor.add(top, policy("top", ("middle", "base"), 1))
    supervisor.add(base, policy("base", (), 1))
    supervisor.add(middle, policy("middle", ("base",), 1))
    supervisor.arrange(("base", "middle", "top"))
    checks.require(supervisor.start_all(clock()), "every service of the set becomes ready")
    checks.require(
        sequence.started == ["base", "middle", "top"],
        "a service starts only after the services it needs are ready",
    )
    checks.require(
        supervisor.state() == SYSTEM_RUNNING
        and len([status for status in supervisor.statuses() if status.state == SERVICE_READY]) == 3,
        "the supervisor reports every service ready",
    )
    checks.require(
        base.handles() == 1 and middle.handles() == 2 and top.handles() == 3,
        "a service receives its registration and exactly the services it declared",
    )
    checks.require(supervisor.stop_all(), "every service stops in order")
    checks.require(
        sequence.stopped == ["top", "middle", "base"],
        "services stop before the services they need",
    )
