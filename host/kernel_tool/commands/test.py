import argparse
import logging
import sys

from kernel_tool.build.native import build_outputs, require_artifacts
from kernel_tool.commands.options import (
    CommandRegistry,
    add_profile_option,
    load_toolchain,
    selected_profile,
)
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.scenarios.bootstrap import BOOTSTRAP
from kernel_tool.scenarios.guest_suites import GUEST_SUITES
from kernel_tool.scenarios.model import Scenario
from kernel_tool.scenarios.report import format_result, suite_document, write_document
from kernel_tool.scenarios.runner import SuiteContext, run_scenario
from kernel_tool.workspace import Workspace

SUITES: dict[str, tuple[Scenario, ...]] = {"bootstrap": BOOTSTRAP, **GUEST_SUITES}

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    test = commands.add_parser(
        "test", help="boot every scenario of a suite and check what the kernel reports"
    )
    add_profile_option(test)
    test.add_argument("--suite", required=True, choices=sorted(SUITES), help="scenario suite")
    test.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="run only this scenario of the suite (repeatable)",
    )
    test.set_defaults(handler=run_suite)


def run_suite(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    suite: str = options.suite
    profile = selected_profile(workspace, options)
    outputs = build_outputs(workspace, profile)
    require_artifacts(outputs)
    scenarios = select_scenarios(SUITES[suite], options.scenario)

    directory = outputs.directory / "scenarios"
    directory.mkdir(parents=True, exist_ok=True)
    context = SuiteContext(
        root=workspace.root,
        profile=profile,
        toolchain=load_toolchain(workspace),
        outputs=outputs,
        directory=directory,
    )

    results = []
    for scenario in scenarios:
        result = run_scenario(scenario, context)
        sys.stdout.write(format_result(result))
        sys.stdout.flush()
        results.append(result)

    report = outputs.directory / "reports" / f"{suite}.json"
    write_document(report, suite_document(suite, profile.name, results))
    failed = [result.name for result in results if not result.passed]
    if failed:
        raise CheckError(
            f"{len(failed)} of {len(results)} scenarios failed: {', '.join(failed)}; see {report}"
        )
    logger.info("%d scenarios passed; report written to %s", len(results), report)
    return ExitCode.OK


def select_scenarios(suite: tuple[Scenario, ...], names: list[str] | None) -> tuple[Scenario, ...]:
    if names is None:
        return suite
    known = {scenario.name for scenario in suite}
    unknown = sorted(set(names) - known)
    if unknown:
        raise CheckError(f"unknown scenarios: {', '.join(unknown)}")
    return tuple(scenario for scenario in suite if scenario.name in names)
