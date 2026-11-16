import pytest

from kernel_core.processes.lifecycle import BLOCKED, DYING, NEW, READY, RUNNING
from kernel_core.scheduling.selection import (
    AGING_THRESHOLD,
    HIGHEST_PRIORITY,
    LOWEST_PRIORITY,
    NO_PROCESS,
    Scheduler,
)
from kernel_protocol.errors.codes import BAD_STATE, INVALID_ARGUMENT, INVALID_HANDLE, KernelError


def error_code(operation, *arguments: int) -> int:
    with pytest.raises(KernelError) as raised:
        operation(*arguments)
    return raised.value.code


def ready_scheduler(priorities: dict[int, int]) -> Scheduler:
    scheduler = Scheduler()
    for handle, priority in priorities.items():
        scheduler.admit(handle, priority)
        scheduler.make_ready(handle)
    return scheduler


def test_processes_of_the_same_priority_run_round_robin() -> None:
    scheduler = ready_scheduler({11: 1, 12: 1, 13: 1})

    assert [scheduler.select() for _ in range(6)] == [11, 12, 13, 11, 12, 13]


def test_higher_priority_runs_before_lower_priority() -> None:
    scheduler = ready_scheduler({21: LOWEST_PRIORITY, 22: HIGHEST_PRIORITY})

    assert scheduler.select() == 22
    assert scheduler.process(22).state == RUNNING
    assert scheduler.process(21).state == READY


def test_waiting_process_is_promoted_until_it_runs() -> None:
    scheduler = ready_scheduler({31: HIGHEST_PRIORITY, 32: HIGHEST_PRIORITY, 33: 1})

    selections = [scheduler.select() for _ in range(AGING_THRESHOLD + 3)]

    assert 33 in selections
    assert selections.index(33) <= AGING_THRESHOLD + 2
    assert scheduler.process(33).effective_priority == 1


def test_blocked_process_leaves_the_cpu_and_returns_when_ready() -> None:
    scheduler = ready_scheduler({41: 0, 42: 0})
    scheduler.select()

    scheduler.block(41)

    assert scheduler.running == NO_PROCESS
    assert scheduler.process(41).state == BLOCKED
    assert scheduler.select() == 42
    scheduler.make_ready(41)
    assert scheduler.select() == 41


def test_exit_removes_a_ready_process_from_its_queue() -> None:
    scheduler = ready_scheduler({51: 2, 52: 2})

    scheduler.exit(51)

    assert scheduler.queued(2) == [52]
    assert scheduler.process(51).state == DYING
    scheduler.reap(51)
    assert scheduler.processes() == [52]


def test_select_without_ready_processes_returns_no_process() -> None:
    scheduler = Scheduler()
    scheduler.admit(61, 0)

    assert scheduler.select() == NO_PROCESS
    assert scheduler.process(61).state == NEW


def test_invalid_requests_report_the_documented_codes() -> None:
    scheduler = ready_scheduler({71: 0})
    scheduler.select()

    assert error_code(scheduler.admit, 71, 0) == BAD_STATE
    assert error_code(scheduler.admit, 72, LOWEST_PRIORITY + 1) == INVALID_ARGUMENT
    assert error_code(scheduler.admit, NO_PROCESS, 0) == INVALID_HANDLE
    assert error_code(scheduler.make_ready, 71) == BAD_STATE
    assert error_code(scheduler.block, 99) == INVALID_HANDLE
    assert error_code(scheduler.reap, 71) == BAD_STATE
