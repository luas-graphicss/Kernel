import hashlib
import multiprocessing
import zlib
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.fuzzing.corpus import (
    CORPUS_DIRECTORY,
    REGRESSION_DIRECTORY,
    entries_file,
    read_entries,
    write_entries,
)
from kernel_tool.fuzzing.engine import Executor, fuzz, replay
from kernel_tool.fuzzing.interpreted import InterpretedExecutor
from kernel_tool.fuzzing.model import Family, Finding, InterpretedTarget, Target, TargetRun
from kernel_tool.fuzzing.native import native_executor
from kernel_tool.fuzzing.registry import target_named, targets_of
from kernel_tool.outcome import CheckError

GUEST_SOURCES = "src"
WORKING_CORPUS = "corpus"
FINDINGS_DIRECTORY = "findings"
TIME_LIMIT_SECONDS = 10.0
DIGEST_CHARACTERS = 16
START_METHOD = "spawn"


@dataclass(frozen=True, slots=True)
class Campaign:
    root: Path
    directory: Path
    harness: Path | None
    seed: int


@dataclass(frozen=True, slots=True)
class Assignment:
    family: Family
    target: str
    budget_seconds: float


def assignments(families: tuple[Family, ...], budget_seconds: float) -> list[Assignment]:
    planned: list[Assignment] = []
    for family in families:
        targets = targets_of(family)
        share = budget_seconds / len(targets)
        planned.extend(Assignment(family, target.name, share) for target in targets)
    return planned


def run_campaign(
    campaign: Campaign, planned: list[Assignment], jobs: int
) -> list[tuple[Target, TargetRun]]:
    if jobs == 1:
        runs = [run_assignment(campaign, assignment) for assignment in planned]
    else:
        context = multiprocessing.get_context(START_METHOD)
        with ProcessPoolExecutor(max_workers=jobs, mp_context=context) as pool:
            runs = list(pool.map(run_assignment, [campaign] * len(planned), planned))
    return [
        (target_named(assignment.family, assignment.target), run)
        for assignment, run in zip(planned, runs, strict=True)
    ]


def run_assignment(campaign: Campaign, assignment: Assignment) -> TargetRun:
    target = target_named(assignment.family, assignment.target)
    working = entries_file(campaign.directory / WORKING_CORPUS, target)
    inputs = (*known_inputs(campaign.root, target), *read_entries(working))
    seed = campaign.seed ^ zlib.crc32(target.name.encode("utf-8"))
    with open_executor(campaign, target) as executor:
        run = fuzz(target, executor, inputs, assignment.budget_seconds, seed)
    write_entries(working, (*read_entries(working), *run.discovered))
    store_findings(campaign.directory, run.findings)
    return run


def replay_known_inputs(campaign: Campaign, target: Target) -> list[Finding]:
    with open_executor(campaign, target) as executor:
        return replay(target, executor, known_inputs(campaign.root, target))[1]


def known_inputs(root: Path, target: Target) -> tuple[bytes, ...]:
    return (
        *target.seeds(),
        *read_entries(entries_file(root / CORPUS_DIRECTORY, target)),
        *read_entries(entries_file(root / REGRESSION_DIRECTORY, target)),
    )


@contextmanager
def open_executor(campaign: Campaign, target: Target) -> Iterator[Executor]:
    if isinstance(target, InterpretedTarget):
        sources = campaign.root / GUEST_SOURCES
        with InterpretedExecutor(target, sources, TIME_LIMIT_SECONDS) as interpreted:
            yield interpreted
    elif campaign.harness is None:
        raise CheckError(f"the native harness was not built for the target {target.name}")
    else:
        with native_executor(campaign.harness, target, TIME_LIMIT_SECONDS) as native:
            yield native


def promote_discoveries(campaign: Campaign, target: Target) -> int:
    versioned = entries_file(campaign.root / CORPUS_DIRECTORY, target)
    working = read_entries(entries_file(campaign.directory / WORKING_CORPUS, target))
    kept = []
    with open_executor(campaign, target) as executor:
        replay(target, executor, known_inputs(campaign.root, target))
        for candidate in sorted(working, key=len):
            execution = executor.execute(candidate)
            if execution.failure is None and execution.found_coverage:
                kept.append(candidate)
    if kept:
        write_entries(versioned, (*read_entries(versioned), *kept))
    return len(kept)


def store_findings(directory: Path, findings: tuple[Finding, ...]) -> None:
    for finding in findings:
        folder = directory / FINDINGS_DIRECTORY / finding.family.value / finding.target
        folder.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(finding.data).hexdigest()[:DIGEST_CHARACTERS]
        (folder / f"{name}.hex").write_text(finding.data.hex() + "\n", encoding="ascii")
        description = f"{finding.failure.kind.value}: {finding.failure.signature}\n\n"
        (folder / f"{name}.txt").write_text(description + finding.failure.detail, encoding="utf-8")
