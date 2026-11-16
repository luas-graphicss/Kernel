import ast
from pathlib import Path

import pytest

from kernel_tool.commands.fault_test import DEFAULT_SEQUENCES
from kernel_tool.commands.test import SUITES
from kernel_tool.faults.stages import (
    REPORTED_FAILURES,
    Stage,
    format_stage,
    matrix_stage,
    sequences_stage,
    trace_stage,
)
from kernel_tool.faults.transactions import TRANSACTIONS
from kernel_tool.outcome import CheckError
from kernel_tool.scenarios.evaluation import check_transcript
from kernel_tool.scenarios.fault_suites import (
    DEVICE_RESET,
    FAULT_SUITES,
    JOURNAL_TRANSACTIONS,
    STORAGE_CRASH,
)
from kernel_tool.scenarios.guest_suites import CASES, VOLUME_REPORT
from kernel_tool.scenarios.model import (
    DataAttachment,
    DataCheck,
    DataDisk,
    DataSource,
    Devices,
    Scenario,
)
from kernel_tool.verification.transcript import read_transcript

REPOSITORY = Path(__file__).resolve().parents[2]
JOURNAL = REPOSITORY / "tests" / "guest" / "programs" / "suites" / "storage" / "journal.py"
REQUIRED_SEQUENCES = 1000
DEVICE_FAILURE = "device: slot=3 state=failed reason=device-needs-reset"
ADMITTED = "policy: admitted=init program=suites.device_reset.main handle=16777216 priority=1"
CLEAN_EXIT = (
    "policy: reaped=init reason=exit value=0 live=0 memory-in-use=0",
    "policy: resources=released",
    "kernel: status=ok",
)


def only_scenario(suite: str) -> Scenario:
    (scenario,) = FAULT_SUITES[suite]
    return scenario


def reset_report(case: str) -> str:
    return f"test: suite={DEVICE_RESET} case={case} checks=4 result=ok"


def reset_transcript(failure_position: int | None) -> str:
    lines = [reset_report(case) for case in CASES[DEVICE_RESET]]
    if failure_position is not None:
        lines.insert(failure_position, DEVICE_FAILURE)
    return "\n".join(("boot: hart=0", ADMITTED, *lines, *CLEAN_EXIT)) + "\n"


def reset_failures(failure_position: int | None) -> list[str]:
    transcript = read_transcript(reset_transcript(failure_position))
    return check_transcript(only_scenario(DEVICE_RESET), transcript)


def declared_transactions() -> int:
    tree = ast.parse(JOURNAL.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "TRANSACTIONS":
            assert isinstance(node.value, ast.Tuple)
            return len(node.value.elts)
    raise AssertionError(f"{JOURNAL} declares no TRANSACTIONS")


def test_fault_suites_are_registered_apart_from_the_test_suites() -> None:
    assert set(FAULT_SUITES) == {"device-reset", "storage-crash"}
    assert {DEVICE_RESET, STORAGE_CRASH} == set(FAULT_SUITES)
    assert not set(FAULT_SUITES) & set(SUITES)
    assert DEFAULT_SEQUENCES >= REQUIRED_SEQUENCES


def test_stalled_device_runs_the_reset_cases_against_a_device_that_never_answers() -> None:
    stalled = only_scenario(DEVICE_RESET)

    assert stalled.arguments == "init=suites.device_reset.main"
    assert stalled.devices == Devices(stalled=True)


def test_the_device_must_report_its_failure_right_before_the_last_reset_case() -> None:
    last = len(CASES[DEVICE_RESET]) - 1

    assert reset_failures(last) == []
    assert len(reset_failures(None)) == 1
    assert len(reset_failures(last + 1)) == 1


def test_flush_trace_writes_a_fresh_traced_volume_once_per_transaction() -> None:
    trace = only_scenario(STORAGE_CRASH)

    assert trace.arguments == "init=suites.storage.journal"
    assert trace.devices.data == DataDisk(
        DataSource.FORMATTED, DataAttachment.TRACED, DataCheck.REPORTED
    )
    assert trace.expected_lines.count(VOLUME_REPORT) == JOURNAL_TRANSACTIONS
    assert declared_transactions() == JOURNAL_TRANSACTIONS


def test_a_stage_report_lists_its_counts_and_the_first_failures() -> None:
    passed = Stage("crash-matrix", {"transactions": 2, "images": 9}, (), [])
    failed = Stage("crash-sequences", {"sequences": 1}, tuple(f"seed {n}" for n in range(30)), {})
    report = format_stage(failed).splitlines()

    assert format_stage(passed) == "PASS crash-matrix transactions=2 images=9\n"
    assert report[0] == "FAIL crash-sequences sequences=1"
    assert report[1] == "  failure: seed 0"
    assert len(report) == 1 + REPORTED_FAILURES
    assert passed.to_document()["passed"] is True
    assert failed.to_document()["passed"] is False


def test_the_matrix_stage_covers_every_minimal_transaction() -> None:
    stage = matrix_stage()

    assert stage.passed
    assert stage.counts["transactions"] == len(TRANSACTIONS)
    assert stage.counts["crash-points"] > stage.counts["transactions"]
    assert stage.counts["images"] > stage.counts["crash-points"]


def test_the_sequence_stage_records_the_seeds_it_ran() -> None:
    stage = sequences_stage(3, 40)

    assert stage.passed
    assert stage.counts["sequences"] == 3
    assert stage.counts["first-seed"] == 40
    assert stage.evidence == {"first_seed": 40, "last_seed": 42, "failed_seeds": []}
    with pytest.raises(CheckError, match="must be positive"):
        sequences_stage(0, 1)


def test_the_trace_stage_needs_the_log_of_the_traced_scenario(tmp_path: Path) -> None:
    with pytest.raises(CheckError, match="did not run"):
        trace_stage(tmp_path, ())
