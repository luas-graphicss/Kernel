import argparse
import json
import logging
import os
import sys
from pathlib import Path

from kernel_tool.commands.options import CommandRegistry
from kernel_tool.fuzzing.campaign import (
    Campaign,
    assignments,
    promote_discoveries,
    replay_known_inputs,
    run_campaign,
)
from kernel_tool.fuzzing.ledger import family_evidence, record_runs
from kernel_tool.fuzzing.model import Family, NativeTarget, Target, TargetRun
from kernel_tool.fuzzing.native import build_harness
from kernel_tool.fuzzing.registry import targets_of
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.workspace import Workspace

FUZZ_DIRECTORY = "fuzz"
REPORT_FILE = "report.json"
SECONDS_PER_HOUR = 3600
DEFAULT_SEED = 1

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    fuzz = commands.add_parser(
        "fuzz", help="mutate boot, interface, storage and network inputs and watch for failures"
    )
    add_family_options(fuzz)
    fuzz.add_argument(
        "--budget-hours",
        type=positive_hours,
        required=True,
        help="hours spent on each selected family, not shared between them",
    )
    fuzz.add_argument(
        "--jobs",
        type=positive_count,
        default=os.cpu_count() or 1,
        help="targets fuzzed at the same time (default: one for each processor)",
    )
    fuzz.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"seed of the mutations (default: {DEFAULT_SEED})",
    )
    fuzz.set_defaults(handler=run_fuzz)

    replay = commands.add_parser(
        "replay-corpus",
        help="run the seeds, the versioned corpus and the regressions once, without mutation",
    )
    add_family_options(replay)
    replay.set_defaults(handler=run_replay)

    promote = commands.add_parser(
        "promote-corpus",
        help="copy the inputs found by fuzz that reach new code into tests/fuzz/corpus",
    )
    add_family_options(promote)
    promote.set_defaults(handler=run_promote)


def add_family_options(parser: argparse.ArgumentParser) -> None:
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="every family")
    selection.add_argument(
        "--family",
        action="append",
        choices=[family.value for family in Family],
        help="one family (repeatable)",
    )


def positive_hours(text: str) -> float:
    hours = float(text)
    if hours <= 0:
        raise argparse.ArgumentTypeError("the budget must be greater than zero")
    return hours


def positive_count(text: str) -> int:
    count = int(text)
    if count <= 0:
        raise argparse.ArgumentTypeError("the count must be greater than zero")
    return count


def selected_families(options: argparse.Namespace) -> tuple[Family, ...]:
    chosen: list[str] | None = options.family
    if chosen is None:
        return tuple(Family)
    return tuple(family for family in Family if family.value in chosen)


def open_campaign(workspace: Workspace, families: tuple[Family, ...], seed: int) -> Campaign:
    targets = [target for family in families for target in targets_of(family)]
    needs_harness = any(isinstance(target, NativeTarget) for target in targets)
    return Campaign(
        root=workspace.root,
        directory=workspace.build_dir / FUZZ_DIRECTORY,
        harness=build_harness(workspace) if needs_harness else None,
        seed=seed,
    )


def run_fuzz(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    families = selected_families(options)
    budget_hours: float = options.budget_hours
    campaign = open_campaign(workspace, families, options.seed)
    planned = assignments(families, budget_hours * SECONDS_PER_HOUR)
    runs = run_campaign(campaign, planned, options.jobs)
    record_runs(campaign.directory, campaign.root, runs)

    for _target, run in runs:
        sys.stdout.write(format_run(run))
    report = campaign.directory / REPORT_FILE
    document = report_document(campaign, families, budget_hours, runs)
    report.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    findings = [
        f"{run.family.value}/{run.target}: {finding.failure.signature}"
        for _target, run in runs
        for finding in run.findings
    ]
    if findings:
        raise CheckError(
            f"fuzzing found {len(findings)} failures; inputs kept under {campaign.directory}:\n"
            + "\n".join(findings)
        )
    logger.info(
        "no failure in %g hours for each family; report written to %s", budget_hours, report
    )
    return ExitCode.OK


def run_replay(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    failures = replay_families(workspace, selected_families(options))
    if failures:
        raise CheckError("known fuzzing inputs fail:\n" + "\n".join(failures))
    logger.info("every known fuzzing input is handled")
    return ExitCode.OK


def replay_families(workspace: Workspace, families: tuple[Family, ...]) -> list[str]:
    campaign = open_campaign(workspace, families, DEFAULT_SEED)
    failures: list[str] = []
    for family in families:
        for target in targets_of(family):
            findings = replay_known_inputs(campaign, target)
            verdict = "FAIL" if findings else "PASS"
            sys.stdout.write(f"{verdict} {family.value}/{target.name} replayed\n")
            failures.extend(
                f"{family.value}/{target.name}: {finding.failure.signature}" for finding in findings
            )
    return failures


def run_promote(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    families = selected_families(options)
    campaign = open_campaign(workspace, families, DEFAULT_SEED)
    for family in families:
        for target in targets_of(family):
            kept = promote_discoveries(campaign, target)
            logger.info("%s/%s: %d inputs added to the corpus", family.value, target.name, kept)
    return ExitCode.OK


def format_run(run: TargetRun) -> str:
    verdict = "FAIL" if run.findings else "PASS"
    return (
        f"{verdict} {run.family.value}/{run.target} executions={run.executions} "
        f"seconds={run.seconds:.1f} corpus={run.population} findings={len(run.findings)}\n"
    )


def report_document(
    campaign: Campaign,
    families: tuple[Family, ...],
    budget_hours: float,
    runs: list[tuple[Target, TargetRun]],
) -> dict[str, object]:
    return {
        "budget_hours": budget_hours,
        "seed": campaign.seed,
        "families": [family_document(campaign, family, runs) for family in families],
    }


def family_document(
    campaign: Campaign, family: Family, runs: list[tuple[Target, TargetRun]]
) -> dict[str, object]:
    evidence = family_evidence(campaign.directory, campaign.root, family)
    return {
        "family": family.value,
        "accumulated_hours": evidence.hours,
        "accumulated_executions": evidence.executions,
        "open_findings": evidence.open_findings,
        "targets": [
            target_document(campaign.directory, run)
            for _target, run in runs
            if run.family is family
        ],
    }


def target_document(directory: Path, run: TargetRun) -> dict[str, object]:
    return {
        "target": run.target,
        "executions": run.executions,
        "seconds": round(run.seconds, 3),
        "corpus": run.population,
        "discovered": len(run.discovered),
        "findings": [
            {
                "kind": finding.failure.kind.value,
                "signature": finding.failure.signature,
                "input_bytes": len(finding.data),
                "kept_under": str(directory / "findings" / run.family.value / run.target),
            }
            for finding in run.findings
        ],
    }
