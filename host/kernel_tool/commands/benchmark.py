import argparse
import logging
import sys
from dataclasses import asdict

from kernel_tool.commands.options import CommandRegistry, add_profile_option, suite_context
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.qualification.budgets import BOOT_TO_SHELL as BOOT_BUDGET
from kernel_tool.qualification.budgets import Verdict, judge
from kernel_tool.qualification.evidence import (
    MEASUREMENTS,
    artifact_identity,
    evidence_file,
    write_evidence,
)
from kernel_tool.qualification.machine import reference_machine
from kernel_tool.qualification.measurements import (
    collector_measurements,
    guest_measurements,
    memory_measurements,
)
from kernel_tool.scenarios.measurement_suites import (
    GUEST_MEASUREMENTS,
    PROCESS_CHURN,
    SYSTEM_MEASUREMENTS,
)
from kernel_tool.scenarios.model import Scenario
from kernel_tool.scenarios.release_suites import BOOT_TO_SHELL
from kernel_tool.scenarios.report import format_result
from kernel_tool.scenarios.runner import ScenarioResult, SuiteContext, run_scenario
from kernel_tool.workspace import Workspace

DEFAULT_BOOTS = 5

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    benchmark = commands.add_parser(
        "benchmark", help="measure boot, memory, latency and collector pauses against the budgets"
    )
    add_profile_option(benchmark)
    benchmark.add_argument(
        "--boots",
        type=int,
        default=DEFAULT_BOOTS,
        help=f"boots timed for the boot budget; the slowest counts (default: {DEFAULT_BOOTS})",
    )
    benchmark.set_defaults(handler=run_benchmark)


def run_benchmark(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    boots: int = options.boots
    if boots <= 0:
        raise CheckError("the number of timed boots must be greater than zero")
    context = suite_context(workspace, options)
    timed = [observe(BOOT_TO_SHELL, context) for _ in range(boots)]
    guest = observe(GUEST_MEASUREMENTS, context)
    churn = observe(PROCESS_CHURN, context)
    system = observe(SYSTEM_MEASUREMENTS, context)

    measured: dict[str, float] = {BOOT_BUDGET: max(boot.duration_seconds for boot in timed)}
    measured |= guest_measurements(guest.transcript)
    measured |= guest_measurements(system.transcript)
    measured |= memory_measurements(system.transcript, context.profile.limits.memory_bytes)
    measured |= collector_measurements((guest.transcript, churn.transcript, system.transcript))
    verdicts = judge(measured)
    for verdict in verdicts:
        sys.stdout.write(format_verdict(verdict))

    report = evidence_file(context.outputs, MEASUREMENTS)
    write_evidence(report, measurement_document(context, measured, verdicts))
    missed = [verdict.metric for verdict in verdicts if not verdict.met]
    if missed:
        raise CheckError(f"budgets not met: {', '.join(missed)}; see {report}")
    logger.info("every budget is met; report written to %s", report)
    return ExitCode.OK


def observe(scenario: Scenario, context: SuiteContext) -> ScenarioResult:
    result = run_scenario(scenario, context)
    sys.stdout.write(format_result(result))
    sys.stdout.flush()
    if not result.passed:
        raise CheckError(f"the measured scenario {result.name} failed; nothing was measured")
    return result


def format_verdict(verdict: Verdict) -> str:
    outcome = "MET" if verdict.met else "MISSED"
    value = "unmeasured" if verdict.value is None else f"{verdict.value:g}"
    return f"{outcome} {verdict.metric} value={value} limit={verdict.limit:g}\n"


def measurement_document(
    context: SuiteContext, measured: dict[str, float], verdicts: list[Verdict]
) -> dict[str, object]:
    return {
        "profile": context.profile.name,
        "artifacts": artifact_identity(context.outputs),
        "machine": reference_machine(context.profile, context.toolchain),
        "measurements": measured,
        "budgets": [asdict(verdict) for verdict in verdicts],
        "passed": all(verdict.met for verdict in verdicts),
    }
