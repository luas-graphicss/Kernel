import json
from pathlib import Path

import pytest

from kernel_tool.fuzzing.campaign import Campaign, assignments, replay_known_inputs
from kernel_tool.fuzzing.corpus import entries_file, read_entries, write_entries
from kernel_tool.fuzzing.ledger import (
    LEDGER_FILE,
    family_evidence,
    ledger_key,
    read_ledger,
    record_runs,
    target_digest,
)
from kernel_tool.fuzzing.model import (
    Failure,
    FailureKind,
    Family,
    Finding,
    InterpretedTarget,
    Target,
    TargetRun,
)
from kernel_tool.fuzzing.registry import TARGETS, targets_of
from kernel_tool.outcome import CheckError

REPOSITORY = Path(__file__).resolve().parents[2]
SECONDS_PER_HOUR = 3600
INTERPRETED = [target for target in TARGETS if isinstance(target, InterpretedTarget)]


def run_of(target: Target, seconds: float, findings: int = 0) -> TargetRun:
    failure = Failure(FailureKind.CRASH, "planted", "detail")
    found = (Finding(target.family, target.name, failure, b""),) * findings
    return TargetRun(target.family, target.name, 10, seconds, 3, (), found)


def test_every_family_has_targets_with_seeds_and_existing_sources() -> None:
    for family in Family:
        targets = targets_of(family)

        assert targets, family
        assert len({target.name for target in targets}) == len(targets)
        for target in targets:
            assert target.seeds(), target.name
            assert all((REPOSITORY / source).exists() for source in target.sources), target.name


def test_the_budget_of_a_family_is_not_shared_with_the_other_families() -> None:
    planned = assignments(tuple(Family), SECONDS_PER_HOUR)

    for family in Family:
        spent = sum(plan.budget_seconds for plan in planned if plan.family is family)

        assert spent == pytest.approx(SECONDS_PER_HOUR)


def test_corpus_entries_are_stored_once_in_a_stable_order(tmp_path: Path) -> None:
    file = entries_file(tmp_path, TARGETS[0])

    write_entries(file, (b"\x02", b"\x01", b"\x02", b""))

    assert read_entries(file) == (b"", b"\x01", b"\x02")
    assert file.parent.name == TARGETS[0].family.value


def test_a_corpus_entry_that_is_not_hexadecimal_is_refused(tmp_path: Path) -> None:
    file = tmp_path / "entries.hex"
    file.write_text("00ff\nnot hexadecimal\n", encoding="ascii")

    with pytest.raises(CheckError, match=r"entries\.hex:2"):
        read_entries(file)


def test_sessions_of_the_same_target_version_accumulate(tmp_path: Path) -> None:
    target = targets_of(Family.STORAGE)[0]

    record_runs(tmp_path, REPOSITORY, [(target, run_of(target, 1800.0))])
    record_runs(tmp_path, REPOSITORY, [(target, run_of(target, 5400.0))])
    evidence = family_evidence(tmp_path, REPOSITORY, Family.STORAGE)

    assert evidence.hours == pytest.approx(2.0)
    assert evidence.targets[target.name].sessions == 2
    assert evidence.open_findings == 0


def test_time_spent_on_an_older_version_of_a_target_does_not_count(tmp_path: Path) -> None:
    target = targets_of(Family.NETWORK)[0]
    record_runs(tmp_path, REPOSITORY, [(target, run_of(target, 7200.0))])
    ledger = tmp_path / LEDGER_FILE
    document = json.loads(ledger.read_text(encoding="utf-8"))
    document["targets"][ledger_key(target)]["digest"] = "0" * 64
    ledger.write_text(json.dumps(document), encoding="utf-8")

    assert family_evidence(tmp_path, REPOSITORY, Family.NETWORK).hours == 0
    record_runs(tmp_path, REPOSITORY, [(target, run_of(target, 60.0))])
    assert read_ledger(tmp_path)[ledger_key(target)].seconds == pytest.approx(60.0)
    assert read_ledger(tmp_path)[ledger_key(target)].digest == target_digest(REPOSITORY, target)


def test_findings_of_the_last_session_stay_open(tmp_path: Path) -> None:
    target = targets_of(Family.BOOT)[0]

    record_runs(tmp_path, REPOSITORY, [(target, run_of(target, 60.0, findings=2))])

    assert family_evidence(tmp_path, REPOSITORY, Family.BOOT).open_findings == 2


@pytest.mark.parametrize("target", INTERPRETED, ids=ledger_key)
def test_seeds_corpus_and_regressions_of_an_interpreted_target_are_handled(
    target: InterpretedTarget, tmp_path: Path
) -> None:
    campaign = Campaign(REPOSITORY, tmp_path, None, 1)

    assert replay_known_inputs(campaign, target) == []
