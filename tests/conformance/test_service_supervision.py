import pytest

from kernel_protocol.configuration.model import ServicePolicy
from kernel_protocol.services.control import (
    SERVICE_BLOCKED,
    SERVICE_DEGRADED,
    SERVICE_READY,
    SERVICE_STOPPED,
    SYSTEM_DEGRADED,
    SYSTEM_RUNNING,
)
from kernel_services.manager.supervision import Supervisor
from kernel_services.manager.units.base import Unit

SECOND = 1_000_000_000
WINDOW = 60 * SECOND


class Recorder:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.stopped: list[str] = []


class FakeUnit(Unit):
    def __init__(self, name: str, recorder: Recorder, failing_starts: int = 0) -> None:
        super().__init__(name)
        self._recorder = recorder
        self._failing_starts = failing_starts
        self.alive = False
        self.stops_cleanly = True

    def start(self, policy: ServicePolicy) -> bool:
        if self._failing_starts > 0:
            self._failing_starts -= 1
            return False
        self.alive = True
        self._recorder.started.append(self.name)
        return True

    def stop(self) -> bool:
        self.alive = False
        self._recorder.stopped.append(self.name)
        return self.stops_cleanly

    def is_alive(self) -> bool:
        return self.alive

    def collect(self) -> str:
        return "reason=killed value=0"

    def crash(self) -> None:
        self.alive = False


def policy(name: str, needs: tuple[str, ...] = (), restarts: int = 2) -> ServicePolicy:
    return ServicePolicy(name, needs, restarts, WINDOW, 2, 0x100000)


def states(supervisor: Supervisor) -> dict[str, int]:
    return {status.name: status.state for status in supervisor.statuses()}


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


def supervise(
    recorder: Recorder, restarts: int = 2, failing_starts: int = 0
) -> tuple[Supervisor, FakeUnit, FakeUnit, FakeUnit]:
    base = FakeUnit("base", recorder, failing_starts)
    client = FakeUnit("client", recorder)
    bystander = FakeUnit("bystander", recorder)
    supervisor = Supervisor()
    supervisor.add(client, policy("client", ("base",)))
    supervisor.add(base, policy("base", (), restarts))
    supervisor.add(bystander, policy("bystander"))
    supervisor.arrange(("base", "bystander", "client"))
    return supervisor, base, client, bystander


def test_services_start_in_dependency_order_and_stop_in_reverse(recorder: Recorder) -> None:
    supervisor, _base, _client, _bystander = supervise(recorder)

    assert supervisor.start_all(0)
    assert recorder.started == ["base", "bystander", "client"]
    assert supervisor.state() == SYSTEM_RUNNING
    assert supervisor.stop_all()
    assert recorder.stopped == ["client", "bystander", "base"]
    assert set(states(supervisor).values()) == {SERVICE_STOPPED}


def test_a_start_that_fails_is_retried_inside_the_restart_budget(recorder: Recorder) -> None:
    supervisor, _base, _client, _bystander = supervise(recorder, restarts=2, failing_starts=2)

    assert supervisor.start_all(0)
    assert recorder.started == ["base", "bystander", "client"]
    assert [status.failures for status in supervisor.statuses() if status.name == "base"] == [2]


def test_a_service_past_its_budget_is_degraded_and_blocks_what_needs_it(
    recorder: Recorder,
) -> None:
    supervisor, _base, _client, _bystander = supervise(recorder, restarts=2, failing_starts=3)

    assert not supervisor.start_all(0)
    assert states(supervisor) == {
        "base": SERVICE_DEGRADED,
        "bystander": SERVICE_READY,
        "client": SERVICE_BLOCKED,
    }
    assert recorder.started == ["bystander"]
    assert supervisor.state() == SYSTEM_DEGRADED
    supervisor.check(SECOND)
    assert recorder.started == ["bystander"]


def test_a_dead_service_is_restarted_with_the_services_that_need_it(recorder: Recorder) -> None:
    supervisor, base, _client, _bystander = supervise(recorder)
    supervisor.start_all(0)

    base.crash()
    supervisor.check(SECOND)

    assert recorder.stopped == ["client"]
    assert recorder.started == ["base", "bystander", "client", "base", "client"]
    assert supervisor.state() == SYSTEM_RUNNING
    assert [status.starts for status in supervisor.statuses()] == [2, 1, 2]


def test_failures_beyond_the_budget_stop_the_restarts_until_the_window_passes(
    recorder: Recorder,
) -> None:
    supervisor, base, _client, bystander = supervise(recorder, restarts=1)
    supervisor.start_all(0)
    base.crash()
    supervisor.check(SECOND)
    assert states(supervisor)["base"] == SERVICE_READY

    base.crash()
    supervisor.check(2 * SECOND)

    assert states(supervisor) == {
        "base": SERVICE_DEGRADED,
        "bystander": SERVICE_READY,
        "client": SERVICE_BLOCKED,
    }
    starts = len(recorder.started)
    for moment in range(3, 10):
        supervisor.check(moment * SECOND)
    assert len(recorder.started) == starts
    assert bystander.is_alive()


def test_a_failure_older_than_the_window_no_longer_counts(recorder: Recorder) -> None:
    supervisor, base, _client, _bystander = supervise(recorder, restarts=1)
    supervisor.start_all(0)
    base.crash()
    supervisor.check(SECOND)

    base.crash()
    supervisor.check(SECOND + WINDOW)

    assert states(supervisor)["base"] == SERVICE_READY
    assert supervisor.state() == SYSTEM_RUNNING


def test_a_unit_that_does_not_stop_cleanly_is_reported(recorder: Recorder) -> None:
    supervisor, base, _client, _bystander = supervise(recorder)
    supervisor.start_all(0)
    base.stops_cleanly = False

    assert not supervisor.stop_all()
    assert recorder.stopped == ["client", "bystander", "base"]


def test_the_starts_reported_for_a_service_are_capped(recorder: Recorder) -> None:
    supervisor, base, _client, _bystander = supervise(recorder, restarts=16)
    supervisor.start_all(0)

    for round_number in range(1, 300):
        base.crash()
        supervisor.check(round_number * 2 * WINDOW)

    reported = {status.name: status.starts for status in supervisor.statuses()}
    assert reported["base"] == 255
    assert reported["bystander"] == 1
