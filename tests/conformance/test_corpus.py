import re

import pytest

from corpus.runner import CASES, REFERENCE_SEED, REFERENCE_TRANSITIONS, report_line, run_reference

SEEDS = (REFERENCE_SEED, 1, 0xDEADBEEF)
DIGEST_PATTERN = re.compile(r"[0-9a-f]{16}")


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize(("name", "run"), CASES, ids=[name for name, _ in CASES])
def test_case_holds_its_invariants_for_every_transition(name: str, run, seed: int) -> None:
    digest = run(seed, REFERENCE_TRANSITIONS)

    assert DIGEST_PATTERN.fullmatch(digest), name


@pytest.mark.parametrize(("name", "run"), CASES, ids=[name for name, _ in CASES])
def test_case_is_deterministic_and_sensitive_to_the_seed(name: str, run) -> None:
    first = run(REFERENCE_SEED, 500)

    assert run(REFERENCE_SEED, 500) == first, name
    assert run(REFERENCE_SEED + 1, 500) != first, name


def test_reference_run_reports_every_case() -> None:
    lines = run_reference()

    assert [line.split()[1] for line in lines] == [f"case={name}" for name, _ in CASES]
    assert all(
        f"seed={REFERENCE_SEED} transitions={REFERENCE_TRANSITIONS}" in line for line in lines
    )


def test_report_line_format_is_stable() -> None:
    assert (
        report_line("identity", 7, 10, "00000000deadbeef")
        == "corpus: case=identity seed=7 transitions=10 digest=00000000deadbeef"
    )
