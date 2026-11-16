import pytest

from runtime_selftest import bytes_case, exceptions_case, integers_case
from runtime_selftest.checks import CheckError, Checks

LANGUAGE_CASES = (
    ("integers", integers_case.run, 17),
    ("bytes", bytes_case.run, 13),
    ("exceptions", exceptions_case.run, 12),
)


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
