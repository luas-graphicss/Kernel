import argparse
import logging
import sys
from dataclasses import asdict

from kernel_tool.build.native import build_outputs
from kernel_tool.commands.matrix import verification_matrix
from kernel_tool.commands.options import CommandRegistry, add_profile_option, selected_profile
from kernel_tool.outcome import CheckError, ExitCode, InfrastructureError
from kernel_tool.qualification.checks import Area, CheckResult, Status, execute, names_with
from kernel_tool.qualification.evidence import (
    VERIFICATION,
    artifact_identity,
    evidence_file,
    write_evidence,
)
from kernel_tool.workspace import Workspace

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    verify = commands.add_parser(
        "verify",
        help="run the verification matrix: host, native, runtime, emulation, "
        "interoperability and recovery",
    )
    add_profile_option(verify)
    selection = verify.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="every area of the matrix")
    selection.add_argument(
        "--area",
        action="append",
        choices=[area.value for area in Area],
        help="one area of the matrix (repeatable)",
    )
    verify.set_defaults(handler=run_verify)


def run_verify(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    profile = selected_profile(workspace, options)
    areas = selected_areas(options)
    results = []
    for check in verification_matrix():
        if check.area in areas:
            result = execute(check, workspace, profile.name)
            sys.stdout.write(format_check(result))
            sys.stdout.flush()
            results.append(result)

    outputs = build_outputs(workspace, profile)
    report = evidence_file(outputs, VERIFICATION)
    document = verification_document(profile.name, areas, results, artifact_identity(outputs))
    write_evidence(report, document)

    failed = names_with(results, Status.FAILED)
    incomplete = names_with(results, Status.INCOMPLETE)
    if failed:
        raise CheckError(
            f"{len(failed)} of {len(results)} checks failed: {', '.join(failed)}; see {report}"
        )
    if incomplete:
        raise InfrastructureError(
            f"{len(incomplete)} checks could not run: {', '.join(incomplete)}; see {report}"
        )
    logger.info("%d checks passed; report written to %s", len(results), report)
    return ExitCode.OK


def selected_areas(options: argparse.Namespace) -> tuple[Area, ...]:
    chosen: list[str] | None = options.area
    if chosen is None:
        return tuple(Area)
    return tuple(area for area in Area if area.value in chosen)


def format_check(result: CheckResult) -> str:
    line = (
        f"{result.status.value.upper()} {result.area.value}/{result.name} "
        f"seconds={result.seconds:.1f}\n"
    )
    if result.detail:
        line += "".join(f"  {detail}\n" for detail in result.detail.splitlines())
    return line


def verification_document(
    profile: str,
    areas: tuple[Area, ...],
    results: list[CheckResult],
    artifacts: dict[str, str],
) -> dict[str, object]:
    return {
        "profile": profile,
        "areas": [area.value for area in areas],
        "whole_matrix": len(areas) == len(Area),
        "artifacts": artifacts,
        "passed": all(result.status is Status.PASSED for result in results),
        "complete": not names_with(results, Status.INCOMPLETE),
        "checks": [asdict(result) for result in results],
    }
