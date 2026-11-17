from pathlib import Path

from kernel_tool.commands.matrix import verification_matrix
from kernel_tool.commands.test import SUITES
from kernel_tool.commands.verify import format_check, verification_document
from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.qualification.checks import (
    Area,
    Check,
    CheckAction,
    CheckResult,
    Status,
    execute,
)
from kernel_tool.scenarios.fault_suites import FAULT_SUITES
from kernel_tool.workspace import Workspace

WORKSPACE = Workspace(Path("/repository"), Path("/build"), Path("/cache"))
PROFILE = "qemu-riscv64"


def passing(_workspace: Workspace, _profile: str) -> None:
    return None


def failing(_workspace: Workspace, _profile: str) -> None:
    raise CheckError("the image differs")


def unavailable(_workspace: Workspace, _profile: str) -> None:
    raise InfrastructureError("the emulator is missing")


def result_of(action: CheckAction) -> CheckResult:
    return execute(Check("subject", Area.NATIVE, action), WORKSPACE, PROFILE)


def test_a_check_passes_fails_or_stays_incomplete() -> None:
    assert result_of(passing).status is Status.PASSED
    assert result_of(failing).status is Status.FAILED
    assert result_of(failing).detail == "the image differs"
    assert result_of(unavailable).status is Status.INCOMPLETE


def test_missing_infrastructure_is_never_reported_as_a_pass() -> None:
    results = [result_of(passing), result_of(unavailable)]

    document = verification_document(PROFILE, tuple(Area), results, {})

    assert document["passed"] is False
    assert document["complete"] is False
    assert format_check(results[1]).startswith("INCOMPLETE native/subject")


def test_a_verification_of_some_areas_does_not_cover_the_whole_matrix() -> None:
    partial = verification_document(PROFILE, (Area.HOST,), [result_of(passing)], {})
    whole = verification_document(PROFILE, tuple(Area), [result_of(passing)], {})

    assert partial["whole_matrix"] is False
    assert whole["whole_matrix"] is True


def test_the_matrix_runs_every_suite_and_every_fault_suite_once() -> None:
    names = [check.name for check in verification_matrix()]

    assert len(set(names)) == len(names)
    assert {f"suite-{suite}" for suite in SUITES} <= set(names)
    assert {f"faults-{suite}" for suite in FAULT_SUITES} <= set(names)
    assert {check.area for check in verification_matrix()} == set(Area)
