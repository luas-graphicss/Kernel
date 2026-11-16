import pytest

from doubles.native_supervisor import NativeSupervisor, Turn
from kernel_core.events.outcomes import (
    EVENT_EXITED,
    EVENT_READY,
    NATIVE_BLOCKED,
    NATIVE_FREE,
    NATIVE_READY,
    RUN_BLOCKED,
    RUN_EXITED,
    RUN_PREEMPTED,
    RUN_SPAWN,
    RUN_STALE,
    RUN_YIELDED,
)
from kernel_core.memory.budget import ResourceProfile
from kernel_core.processes.admission import ProcessRegistry
from kernel_core.processes.lifecycle import READY
from kernel_core.supervision.supervisor import (
    QUANTUM_NANOSECONDS,
    QUOTA_SLACK_FRAMES,
    TRACE_LIMIT,
    Supervisor,
)
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    LIMIT_EXCEEDED,
    OUT_OF_MEMORY,
    KernelError,
)
from kernel_protocol.processes.status import WAIT_REASON_EXIT, WAIT_REASON_KILLED

MIB = 1 << 20
FRAME_BYTES = 4096
CAPABILITIES = 128
IPC_PENDING_BYTES = MIB
BUDGET_BYTES = 64 * MIB
PROGRAM = "kernel_services.init.main"
INIT_PRIORITY = 1
SERVICE = ("kernel_services.echo.main", 2, 0x40000, 0)
WORKER = ("suites.scheduling.worker", 3, 0x40000, 0)
UNKNOWN = 0x7777


class Booted:
    def __init__(self, native: NativeSupervisor, traces: bool = False) -> None:
        profile = ResourceProfile(
            (256 * MIB, 8, 8 * MIB, 4 * MIB, CAPABILITIES, IPC_PENDING_BYTES, 16 * MIB)
        )
        self.native = native
        self.registry = ProcessRegistry(profile, BUDGET_BYTES)
        self.supervisor = Supervisor(self.registry, FRAME_BYTES, traces)
        self.frames = native.footprint_frames + QUOTA_SLACK_FRAMES

    def start(self) -> int:
        return self.supervisor.start_init(PROGRAM, INIT_PRIORITY)

    def outcome(self) -> tuple[int, int]:
        return self.supervisor.init_exit.reason, self.supervisor.init_exit.value


@pytest.fixture
def booted(native_supervisor: NativeSupervisor) -> Booted:
    return Booted(native_supervisor)


def exits(value: int = 0, events=()) -> Turn:
    return Turn(RUN_EXITED, WAIT_REASON_EXIT, value, events)


def test_first_process_is_created_with_the_quota_of_the_profile(booted: Booted) -> None:
    init = booted.start()

    assert booted.native.spawned == [(PROGRAM, 0, booted.frames, CAPABILITIES, IPC_PENDING_BYTES)]
    assert booted.registry.live() == 1
    assert booted.registry.memory_in_use() == booted.frames * FRAME_BYTES
    assert booted.registry.scheduler.process(init).state == READY


def test_first_process_the_native_side_refuses_is_reported_with_its_code(booted: Booted) -> None:
    booted.native.spawn_error = OUT_OF_MEMORY

    with pytest.raises(KernelError) as raised:
        booted.start()

    assert raised.value.code == OUT_OF_MEMORY
    assert booted.registry.live() == 0
    assert booted.registry.memory_in_use() == 0


def test_heap_that_fits_no_process_is_refused_before_anything_is_created(booted: Booted) -> None:
    booted.native.footprint_frames = 0

    with pytest.raises(KernelError) as raised:
        booted.start()

    assert raised.value.code == LIMIT_EXCEEDED
    assert booted.native.spawned == []


def test_init_runs_until_it_exits_and_its_outcome_is_kept(
    booted: Booted, capsys: pytest.CaptureFixture[str]
) -> None:
    init = booted.start()
    booted.native.script(init, Turn(RUN_PREEMPTED), Turn(RUN_YIELDED), exits(7))

    booted.supervisor.run()

    assert booted.native.ran == [init, init, init]
    assert booted.native.quanta == {QUANTUM_NANOSECONDS}
    assert booted.outcome() == (WAIT_REASON_EXIT, 7)
    assert booted.native.released == [init]
    assert (booted.registry.live(), booted.registry.memory_in_use()) == (0, 0)
    assert booted.supervisor.deadlocks == 0
    assert capsys.readouterr().out == ""


def test_spawn_request_is_admitted_with_a_quota_and_scheduled(booted: Booted) -> None:
    init = booted.start()
    service = init + 1
    booted.native.script(init, Turn(RUN_SPAWN, spawn=SERVICE), Turn(RUN_BLOCKED), exits())
    booted.native.script(service, exits(events=((EVENT_READY, init),)))

    booted.supervisor.run()

    assert booted.native.admitted == [(booted.frames, CAPABILITIES, IPC_PENDING_BYTES)]
    assert booted.native.rejected == []
    assert booted.native.ran == [init, init, service, init]
    assert booted.native.released == [service, init]
    assert booted.outcome() == (WAIT_REASON_EXIT, 0)


@pytest.mark.parametrize(
    ("asked", "code"),
    [
        (("kernel_services.echo.main", 2, 8 * MIB, 0), LIMIT_EXCEEDED),
        (("kernel_services.echo.main", 2, 0x40000, 128 * MIB), LIMIT_EXCEEDED),
        (("kernel_services.echo.main", 0, 0x40000, 0), ACCESS_DENIED),
    ],
    ids=["heap-above-the-limit", "memory-above-the-budget", "more-urgent-than-its-parent"],
)
def test_spawn_request_outside_the_quota_is_rejected_with_its_code(
    booted: Booted, asked: tuple[str, int, int, int], code: int
) -> None:
    init = booted.start()
    booted.native.script(init, Turn(RUN_SPAWN, spawn=asked), exits())

    booted.supervisor.run()

    assert booted.native.rejected == [code]
    assert booted.native.admitted == []
    assert booted.native.ran == [init, init]


def test_spawn_the_native_side_refuses_is_not_scheduled(booted: Booted) -> None:
    init = booted.start()
    booted.native.admission_error = OUT_OF_MEMORY
    booted.native.script(init, Turn(RUN_SPAWN, spawn=SERVICE), exits())

    booted.supervisor.run()

    assert booted.native.admitted == [(booted.frames, CAPABILITIES, IPC_PENDING_BYTES)]
    assert booted.native.ran == [init, init]
    assert booted.native.released == [init]


def test_blocked_caller_lends_its_priority_to_the_process_it_waits_on(booted: Booted) -> None:
    init = booted.start()
    worker, service = init + 1, init + 2
    booted.native.script(
        init,
        Turn(RUN_SPAWN, spawn=WORKER),
        Turn(RUN_SPAWN, spawn=SERVICE),
        Turn(RUN_BLOCKED, worker),
        exits(),
    )
    booted.native.script(worker, Turn(RUN_PREEMPTED, events=((EVENT_READY, init),)))
    booted.native.script(service)

    booted.supervisor.run()

    assert booted.native.ran == [init, init, init, worker, init]
    assert booted.native.killed == [worker, service]
    assert booted.native.released == [init, worker, service]


def test_wait_on_something_that_is_not_a_process_donates_nothing(booted: Booted) -> None:
    init = booted.start()
    service = init + 1
    booted.native.script(init, Turn(RUN_SPAWN, spawn=SERVICE), Turn(RUN_BLOCKED, UNKNOWN), exits())
    booted.native.script(service, Turn(RUN_YIELDED, events=((EVENT_READY, init),)))

    booted.supervisor.run()

    assert booted.native.ran == [init, init, service, init]


def test_process_killed_by_another_is_reaped_from_its_exit_event(booted: Booted) -> None:
    init = booted.start()
    service = init + 1
    reported = ((EVENT_READY, UNKNOWN), (EVENT_READY, init), (EVENT_EXITED, service))
    booted.native.script(
        init, Turn(RUN_SPAWN, spawn=SERVICE), Turn(RUN_PREEMPTED, events=reported), exits()
    )
    booted.native.script(service)

    booted.supervisor.run()

    assert booted.native.ran == [init, init, init]
    assert booted.native.released == [service, init]
    assert booted.native.killed == []


def test_processes_that_all_wait_forever_are_stopped_and_counted(booted: Booted) -> None:
    init = booted.start()
    service = init + 1
    booted.native.script(init, Turn(RUN_SPAWN, spawn=SERVICE), Turn(RUN_BLOCKED, service))
    booted.native.script(service, Turn(RUN_BLOCKED, init))

    booted.supervisor.run()

    assert booted.supervisor.deadlocks == 1
    assert booted.native.killed == [init, service]
    assert booted.native.released == [init, service]
    assert booted.registry.live() == 0
    assert booted.outcome() == (WAIT_REASON_KILLED, 0)


def test_supervisor_idles_until_an_event_wakes_a_sleeper(booted: Booted) -> None:
    init = booted.start()
    booted.native.script(init, Turn(RUN_BLOCKED), exits())
    booted.native.interrupts = [
        lambda: None,
        lambda: booted.native.events.append((EVENT_READY, init)),
    ]

    booted.supervisor.run()

    assert booted.native.ran == [init, init]
    assert booted.native.interrupts == []
    assert booted.supervisor.deadlocks == 0


def test_lost_events_are_recovered_from_the_native_states(booted: Booted) -> None:
    init = booted.start()
    service, worker = init + 1, init + 2

    def lose_events() -> None:
        booted.native.overflowed = True
        booted.native.states[init] = NATIVE_READY
        booted.native.states[service] = NATIVE_FREE

    booted.native.script(
        init,
        Turn(RUN_SPAWN, spawn=SERVICE),
        Turn(RUN_SPAWN, spawn=WORKER),
        Turn(RUN_BLOCKED),
        exits(),
    )
    booted.native.script(service, Turn(RUN_BLOCKED))
    booted.native.script(worker, Turn(RUN_BLOCKED))
    booted.native.interrupts = [lose_events]

    booted.supervisor.run()

    assert booted.native.ran == [init, init, init, service, worker, init]
    assert booted.native.released == [service, init, worker]
    assert booted.native.killed == [worker]


def test_init_found_dead_while_recovering_lost_events_stops_everything_once(
    booted: Booted,
) -> None:
    init = booted.start()
    service = init + 1

    def lose_events() -> None:
        booted.native.overflowed = True
        booted.native.states[init] = NATIVE_FREE

    booted.native.script(init, Turn(RUN_SPAWN, spawn=SERVICE), Turn(RUN_BLOCKED))
    booted.native.script(service, Turn(RUN_BLOCKED))
    booted.native.interrupts = [lose_events]

    booted.supervisor.run()

    assert booted.native.released == [init, service]
    assert booted.native.killed == [service]
    assert booted.outcome() == (WAIT_REASON_KILLED, 0)
    assert booted.supervisor.deadlocks == 0


def test_stale_run_follows_the_native_state(booted: Booted) -> None:
    init = booted.start()
    blocked, gone = init + 1, init + 2
    booted.native.script(
        init,
        Turn(RUN_SPAWN, spawn=SERVICE),
        Turn(RUN_SPAWN, spawn=SERVICE),
        Turn(RUN_BLOCKED),
        exits(),
    )
    booted.native.script(blocked, Turn(RUN_STALE, state=NATIVE_BLOCKED))
    booted.native.script(gone, Turn(RUN_STALE, state=NATIVE_FREE, events=((EVENT_READY, init),)))

    booted.supervisor.run()

    assert booted.native.ran == [init, init, init, blocked, gone, init]
    assert booted.native.released == [gone, init, blocked]
    assert booted.native.killed == [blocked]


def test_trace_reports_each_decision_up_to_its_limit(
    native_supervisor: NativeSupervisor, capsys: pytest.CaptureFixture[str]
) -> None:
    booted = Booted(native_supervisor, traces=True)
    init = booted.start()
    preempted = [Turn(RUN_PREEMPTED) for _ in range(TRACE_LIMIT + 5)]
    native_supervisor.script(init, *preempted, exits())

    booted.supervisor.run()

    assert (
        capsys.readouterr().out.splitlines()
        == [f"sched: run={init} priority={INIT_PRIORITY} result=preempted"] * TRACE_LIMIT
    )
