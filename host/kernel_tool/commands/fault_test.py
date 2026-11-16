import argparse
import logging
import sys

from kernel_tool.commands.options import CommandRegistry, add_profile_option, suite_context
from kernel_tool.faults.stages import (
    Stage,
    format_stage,
    matrix_stage,
    sequences_stage,
    trace_stage,
)
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.scenarios.fault_suites import FAULT_SUITES, STORAGE_CRASH
from kernel_tool.scenarios.report import format_result, suite_document, write_document
from kernel_tool.scenarios.runner import ScenarioResult, SuiteContext, run_scenario
from kernel_tool.workspace import Workspace

DEFAULT_SEQUENCES = 1000
DEFAULT_SEED = 1

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    fault = commands.add_parser(
        "fault-test", help="inject storage and device faults and check what survives them"
    )
    add_profile_option(fault)
    fault.add_argument("--suite", required=True, choices=sorted(FAULT_SUITES), help="fault suite")
    fault.add_argument(
        "--sequences",
        type=int,
        default=DEFAULT_SEQUENCES,
        help=f"generated sequences of storage-crash (default: {DEFAULT_SEQUENCES})",
    )
    fault.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"seed of the first generated sequence (default: {DEFAULT_SEED})",
    )
    fault.set_defaults(handler=run_fault_suite)


def run_fault_suite(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    suite: str = options.suite
    context = suite_context(workspace, options)
    results = []
    for scenario in FAULT_SUITES[suite]:
        result = run_scenario(scenario, context)
        sys.stdout.write(format_result(result))
        sys.stdout.flush()
        results.append(result)

    stages = []
    if suite == STORAGE_CRASH:
        for stage in storage_crash_stages(context, results[0], options.sequences, options.seed):
            sys.stdout.write(format_stage(stage))
            sys.stdout.flush()
            stages.append(stage)

    report = context.outputs.directory / "reports" / f"{suite}.json"
    document = suite_document(suite, context.profile.name, results)
    failed = [result.name for result in results if not result.passed]
    failed.extend(stage.name for stage in stages if not stage.passed)
    document["stages"] = [stage.to_document() for stage in stages]
    document["passed"] = not failed
    write_document(report, document)

    if failed:
        raise CheckError(f"fault suite {suite} failed: {', '.join(failed)}; see {report}")
    logger.info("fault suite %s passed; report written to %s", suite, report)
    return ExitCode.OK


def storage_crash_stages(
    context: SuiteContext, traced: ScenarioResult, sequences: int, seed: int
) -> list[Stage]:
    stages = [matrix_stage(), sequences_stage(sequences, seed)]
    if traced.passed:
        stages.append(trace_stage(context.directory, traced.transcript))
    return stages
