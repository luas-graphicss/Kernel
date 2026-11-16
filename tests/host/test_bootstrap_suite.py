import re

import pytest

from kernel_tool.commands.test import SUITES, select_scenarios
from kernel_tool.outcome import CheckError
from kernel_tool.scenarios.bootstrap import BOOTSTRAP
from kernel_tool.scenarios.model import Deadline, Image
from kernel_tool.verification.transcript import KernelStatus

REQUIRED = {
    "boot",
    "runtime-selftest",
    "device-tree-too-large",
    "device-tree-without-memory",
    "insufficient-memory",
    "incompatible-segment",
    "user-fault",
    "supervisor-trap",
    "runtime-trap",
}


def test_suite_contains_every_required_scenario_once() -> None:
    names = [scenario.name for scenario in BOOTSTRAP]

    assert set(names) == REQUIRED
    assert len(names) == len(set(names))
    assert SUITES["bootstrap"] is BOOTSTRAP


def test_every_pattern_compiles_and_every_scenario_asserts_something() -> None:
    for scenario in BOOTSTRAP:
        assert scenario.expected_lines, scenario.name
        for pattern in (*scenario.expected_lines, *scenario.forbidden_lines):
            re.compile(pattern)


def test_only_the_valid_boots_expect_success() -> None:
    succeeding = {
        scenario.name for scenario in BOOTSTRAP if scenario.expected_status is KernelStatus.OK
    }

    assert succeeding == {"boot", "runtime-selftest"}


def test_valid_image_is_booted_repeatedly() -> None:
    boot = next(scenario for scenario in BOOTSTRAP if scenario.name == "boot")

    assert boot.repeats >= 3
    assert boot.image is Image.KERNEL


def test_selftest_compares_the_corpus_within_its_own_deadline() -> None:
    selftest = next(scenario for scenario in BOOTSTRAP if scenario.name == "runtime-selftest")

    assert selftest.compares_corpus
    assert selftest.deadline is Deadline.SELFTEST
    assert selftest.image is Image.SELFTEST


def test_both_supervisor_traps_expect_the_same_report_from_different_states() -> None:
    plain, exhausted = (
        next(scenario for scenario in BOOTSTRAP if scenario.name == name)
        for name in ("supervisor-trap", "runtime-trap")
    )

    assert plain.expected_lines == exhausted.expected_lines
    assert plain.arguments != exhausted.arguments
    assert plain.image is exhausted.image is Image.SELFTEST


def test_selection_keeps_suite_order_and_rejects_unknown_names() -> None:
    selected = select_scenarios(BOOTSTRAP, ["user-fault", "boot"])

    assert [scenario.name for scenario in selected] == ["boot", "user-fault"]
    assert select_scenarios(BOOTSTRAP, None) is BOOTSTRAP
    with pytest.raises(CheckError, match="unknown scenarios: missing"):
        select_scenarios(BOOTSTRAP, ["boot", "missing"])
