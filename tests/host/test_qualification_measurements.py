import pytest

from kernel_tool.outcome import CheckError
from kernel_tool.qualification.budgets import (
    BUDGETS,
    COLLECTOR_LONGEST_PAUSE,
    COLLECTOR_PAUSE,
    IDLE_MEMORY,
    IPC_ROUND_TRIP,
    LOADED_MEMORY,
    judge,
)
from kernel_tool.qualification.measurements import (
    COLLECTIONS,
    collector_measurements,
    guest_measurements,
    memory_measurements,
)

MEMORY_BYTES = 1000000
IDLE = "kernel> mem: frames-usable=100 frames-free=90 frames-reserved=2 bytes-free=900000"
LOADED = "mem: frames-usable=100 frames-free=60 frames-reserved=2 bytes-free=600000"
QUIET = (
    "policy: collector=measured collections=0 pause-total-us=0 pause-p99-us=0 pause-longest-us=0"
)
BUSY = (
    "policy: collector=measured collections=3 pause-total-us=7044 "
    "pause-p99-us=2671 pause-longest-us=2671"
)
BUSIER = (
    "policy: collector=measured collections=2 pause-total-us=9000 "
    "pause-p99-us=4000 pause-longest-us=5000"
)


def test_a_measure_line_yields_its_percentiles_by_name() -> None:
    lines = (
        "kernel> measure: name=ipc-round-trip samples=10000 p50-us=913 p99-us=1327 max-us=5073",
    )

    measured = guest_measurements(lines)

    assert measured[IPC_ROUND_TRIP] == 1327
    assert measured["ipc-round-trip-samples"] == 10000
    assert measured["ipc-round-trip-max-us"] == 5073


def test_committed_memory_is_what_is_not_free_before_and_under_load() -> None:
    measured = memory_measurements((IDLE, "other", LOADED), MEMORY_BYTES)

    assert measured == {IDLE_MEMORY: 100000, LOADED_MEMORY: 400000}


def test_a_session_without_both_memory_reports_is_not_measured() -> None:
    with pytest.raises(CheckError, match="1 times instead of 2"):
        memory_measurements((IDLE,), MEMORY_BYTES)


def test_collector_pauses_are_the_worst_among_the_sessions() -> None:
    measured = collector_measurements(((QUIET,), (BUSY,), ("noise", BUSIER)))

    assert measured == {COLLECTIONS: 5, COLLECTOR_PAUSE: 4000, COLLECTOR_LONGEST_PAUSE: 5000}


def test_a_collector_that_never_ran_leaves_its_budget_unmeasured() -> None:
    measured = collector_measurements(((QUIET,), (QUIET,)))
    verdicts = {verdict.metric: verdict for verdict in judge(measured)}

    assert measured == {COLLECTIONS: 0}
    assert verdicts[COLLECTOR_PAUSE].value is None
    assert not verdicts[COLLECTOR_PAUSE].met


def test_a_session_that_hides_the_collector_report_is_refused() -> None:
    with pytest.raises(CheckError, match="did not report the supervisor collector"):
        collector_measurements(((BUSY,), ("nothing",)))


def test_a_budget_is_met_only_at_or_below_its_limit() -> None:
    at_limit = {budget.metric: budget.limit for budget in BUDGETS}
    above = at_limit | {IPC_ROUND_TRIP: at_limit[IPC_ROUND_TRIP] + 1}

    assert all(verdict.met for verdict in judge(at_limit))
    assert [verdict.metric for verdict in judge(above) if not verdict.met] == [IPC_ROUND_TRIP]
