import re
from pathlib import Path

from kernel_tool.commands.test import SUITES
from kernel_tool.scenarios.fault_suites import FAULT_SUITES

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
SUITE_STEP = re.compile(
    r"^\s+run: sh \.github/scripts/classify-exit\.sh uv run kernel-tool "
    r"(?P<command>test|fault-test) --profile \S+ --suite (?P<suite>[a-z-]+)$"
)
TOLERATED_FAILURE = "continue-on-error"


def workflow_lines() -> list[str]:
    return WORKFLOW.read_text(encoding="utf-8").splitlines()


def suites_run_by(command: str) -> list[str]:
    steps = (SUITE_STEP.match(line) for line in workflow_lines())
    return sorted(step["suite"] for step in steps if step and step["command"] == command)


def test_the_workflow_runs_every_scenario_suite_exactly_once() -> None:
    assert suites_run_by("test") == sorted(SUITES)


def test_the_workflow_runs_every_fault_suite_exactly_once() -> None:
    assert suites_run_by("fault-test") == sorted(FAULT_SUITES)


def test_no_step_of_the_workflow_tolerates_a_failure() -> None:
    assert not [line for line in workflow_lines() if TOLERATED_FAILURE in line]
