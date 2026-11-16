import pytest

from kernel_services.init.main import (
    ALLOCATION_ROUNDS,
    BLOCK_BYTES,
    EXPECTED_CHECKSUM,
    churn_heap,
)
from kernel_services.init.main import main as init_main
from runtime_selftest import bytes_case, exceptions_case, integers_case
from runtime_selftest.checks import CheckError, Checks

LANGUAGE_CASES = (
    ("integers", integers_case.run, 17),
    ("bytes", bytes_case.run, 13),
    ("exceptions", exceptions_case.run, 12),
)


def test_init_checksum_matches_the_value_frozen_in_the_image() -> None:
    assert churn_heap(ALLOCATION_ROUNDS) == EXPECTED_CHECKSUM
    assert churn_heap(ALLOCATION_ROUNDS - 1) != EXPECTED_CHECKSUM


def test_init_reports_success_and_what_it_allocated(capsys: pytest.CaptureFixture[str]) -> None:
    assert init_main() is True

    assert capsys.readouterr().out.splitlines() == [
        "init: runtime=micropython privilege=user",
        f"init: allocated-bytes={ALLOCATION_ROUNDS * BLOCK_BYTES} "
        f"checksum={EXPECTED_CHECKSUM} expected={EXPECTED_CHECKSUM}",
    ]


@pytest.mark.parametrize(
    ("run", "expected_checks"),
    [(run, count) for _, run, count in LANGUAGE_CASES],
    ids=[name for name, _, _ in LANGUAGE_CASES],
)
def test_language_cases_hold_on_cpython_with_the_guest_check_count(run, expected_checks) -> None:
    checks = Checks()

    run(checks)

    assert checks.passed == expected_checks


def test_failed_check_stops_the_case() -> None:
    checks = Checks()
    checks.require(True, "holds")

    with pytest.raises(CheckError, match="does not hold"):
        checks.require(False, "does not hold")

    assert checks.passed == 1
