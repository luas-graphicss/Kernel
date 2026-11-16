import ast
import re
from pathlib import Path

import pytest

from kernel_tool.commands.test import SUITES
from kernel_tool.scenarios.evaluation import check_transcript
from kernel_tool.scenarios.fault_suites import FAULT_SUITES
from kernel_tool.scenarios.guest_suites import CASES, CYCLES_CASE, GUEST_SUITES, MEASURED_CYCLES
from kernel_tool.scenarios.model import BootModule, Deadline, Image, Scenario
from kernel_tool.scenarios.network_suites import NETWORK_SUITES
from kernel_tool.scenarios.system_suites import SUPERVISION_SCENARIO, SYSTEM_SUITES
from kernel_tool.verification.transcript import read_transcript

REPOSITORY = Path(__file__).resolve().parents[2]
PROGRAMS = REPOSITORY / "tests" / "guest" / "programs"
REQUIRED = {
    "memory",
    "processes",
    "capabilities",
    "ipc",
    "scheduling",
    "devices",
    "vfs",
    "storage",
}
TESTS_IMAGE_PROGRAMS = {
    "suites.capabilities.main",
    "suites.device_reset.main",
    "suites.devices.main",
    "suites.ipc.main",
    "suites.memory.main",
    "suites.network.faults",
    "suites.network.interop",
    "suites.network.main",
    "suites.processes.cycles",
    "suites.processes.main",
    "suites.scheduling.main",
    "suites.services.main",
    "suites.storage.journal",
    "suites.storage.main",
    "suites.storage.reader",
    "suites.storage.writer",
    "suites.supervision.main",
    "suites.vfs.main",
}
INIT_OPTION = "init="
CLEAN_EXIT = (
    "policy: reaped=init reason=exit value=0 live=0 memory-in-use=0",
    "policy: resources=released",
    "kernel: status=ok",
)
FAILURE_REPORTS = (
    'test: suite=ipc case=deadlines result=failed check="the endpoint stays empty"',
    "test: suite=ipc case=deadlines result=failed error=TIMED_OUT",
    "test: suite=memory case=shared-buffers result=leaked buffers=0->1",
    "policy: resources=leaked frames-free=62999->62998",
    "policy: stopped=deadlock occurrences=1",
    "panic: reason=unexpected-supervisor-trap",
    "trap: mode=supervisor cause=illegal-instruction",
    "Traceback (most recent call last):",
)
EXPECTED_REPORTS = (
    "user: fault cause=load-page-fault scause=0x000000000000000d sepc=0x0000000040012350 "
    "stval=0x0000000000000000 process=1",
    "test: suite=memory case=forbidden-access checks=18 result=ok",
)
TRACED_BOOT = (
    "boot: hart=0",
    "policy: admitted=init program=kernel_services.init.main handle=16777216 priority=1",
    "sched: run=16777216 priority=1 result=preempted",
    "sched: run=16777216 priority=1 result=spawn",
    "sched: run=16777216 priority=1 result=blocked",
    "sched: run=16777217 priority=2 result=preempted",
    "sched: run=16777216 priority=1 result=blocked",
    "sched: run=16777217 priority=1 result=preempted",
    "sched: run=16777216 priority=1 result=blocked",
    "sched: run=16777217 priority=2 result=exited",
    "sched: run=16777216 priority=1 result=exited",
    *CLEAN_EXIT,
)


def scenario(suite: str, name: str) -> Scenario:
    return next(candidate for candidate in GUEST_SUITES[suite] if candidate.name == name)


def every_scenario() -> list[Scenario]:
    suites = (
        *GUEST_SUITES.values(),
        *FAULT_SUITES.values(),
        *NETWORK_SUITES.values(),
        (SUPERVISION_SCENARIO,),
    )
    return [candidate for scenarios in suites for candidate in scenarios]


def case_program(suite: str) -> str:
    return f"suites.{suite.replace('-', '_')}.main"


def program_file(module: str) -> Path:
    return PROGRAMS.joinpath(*module.split(".")).with_suffix(".py")


def declared_cases(module: str) -> tuple[str, ...]:
    tree = ast.parse(program_file(module).read_text(encoding="utf-8"))
    return tuple(
        node.elts[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Tuple)
        and len(node.elts) == 2
        and isinstance(node.elts[0], ast.Constant)
        and isinstance(node.elts[0].value, str)
        and isinstance(node.elts[1], ast.Attribute | ast.Name)
    )


def reported_by(suite: str, cases: tuple[str, ...]) -> str:
    lines = (
        "boot: hart=0",
        f"policy: admitted=init program=suites.{suite}.main handle=16777216 priority=1",
        *(f"test: suite={suite} case={case} checks=3 result=ok" for case in cases),
        *CLEAN_EXIT,
    )
    return "\n".join(lines) + "\n"


def failures(candidate: Scenario, serial_output: str) -> list[str]:
    return check_transcript(candidate, read_transcript(serial_output))


def test_every_required_suite_is_registered_next_to_bootstrap() -> None:
    assert set(GUEST_SUITES) == REQUIRED
    assert set(SUITES) == REQUIRED | {"bootstrap"} | set(NETWORK_SUITES) | set(SYSTEM_SUITES)
    for name in REQUIRED:
        assert SUITES[name] is GUEST_SUITES[name]


@pytest.mark.parametrize("suite", sorted(CASES))
def test_host_expects_every_case_the_guest_program_declares(suite: str) -> None:
    assert declared_cases(case_program(suite)) == CASES[suite]


@pytest.mark.parametrize("suite", sorted(REQUIRED))
def test_a_transcript_with_every_case_passes_the_scenario(suite: str) -> None:
    assert failures(scenario(suite, "cases"), reported_by(suite, CASES[suite])) == []


@pytest.mark.parametrize("suite", sorted(REQUIRED))
def test_a_case_that_is_missing_or_failed_fails_the_scenario(suite: str) -> None:
    cases = scenario(suite, "cases")
    last = CASES[suite][-1]
    failed = reported_by(suite, CASES[suite]).replace(
        f"case={last} checks=3 result=ok", f'case={last} result=failed check="it holds"'
    )

    assert any(
        last in failure for failure in failures(cases, reported_by(suite, CASES[suite][:-1]))
    )
    assert any("forbidden pattern" in failure for failure in failures(cases, failed))


@pytest.mark.parametrize("line", FAILURE_REPORTS)
def test_reports_of_failure_are_forbidden_in_every_scenario(line: str) -> None:
    for candidate in every_scenario():
        assert any(re.search(pattern, line) for pattern in candidate.forbidden_lines)


@pytest.mark.parametrize("line", EXPECTED_REPORTS)
def test_faults_of_adversarial_programs_and_passing_cases_are_allowed(line: str) -> None:
    for candidate in every_scenario():
        assert not any(re.search(pattern, line) for pattern in candidate.forbidden_lines)


def test_every_program_is_frozen_in_the_tests_image() -> None:
    manifest = (PROGRAMS / "manifest.py").read_text(encoding="utf-8")
    booted = [
        candidate for candidate in every_scenario() if candidate.boot_module is BootModule.TESTS
    ]

    modules = set()
    for candidate in booted:
        assert candidate.arguments is not None
        module = candidate.arguments.removeprefix(INIT_OPTION)
        modules.add(module)
        assert program_file(module).is_file()
        assert '"' + "/".join(module.split(".")[1:]) + '.py"' in manifest
    assert modules == TESTS_IMAGE_PROGRAMS


def test_cycles_run_under_the_soak_deadline_and_report_how_many_completed() -> None:
    cycles = scenario("processes", "cycles")
    source = program_file("suites.processes.cycles").read_text(encoding="utf-8")

    assert cycles.deadline is Deadline.SOAK
    assert cycles.arguments == "init=suites.processes.cycles"
    assert declared_cases("suites.processes.cycles") == (CYCLES_CASE,)
    assert f"MEASURED_CYCLES = {MEASURED_CYCLES}\n" in source
    assert any(f"completed={MEASURED_CYCLES} " in pattern for pattern in cycles.expected_lines)
    assert all(
        candidate.deadline is (Deadline.BOOT if candidate.network is None else Deadline.SESSION)
        for candidate in every_scenario()
        if candidate is not cycles
    )


def test_spawn_failures_need_refusals_that_leave_nothing_behind() -> None:
    probe = scenario("processes", "spawn-failures")
    report = (
        "boot: hart=0\nselftest: probe=spawn-failure refusals={} result={}\nkernel: status=ok\n"
    )

    assert probe.image is Image.SELFTEST
    assert probe.boot_module is BootModule.INIT
    assert probe.arguments == "probe=spawn-failure"
    assert failures(probe, report.format(276, "ok")) == []
    assert failures(probe, report.format(0, "ok")) != []
    assert failures(probe, report.format(12, "refusal-leaked")) != []
    assert failures(probe, report.format(12, "teardown-leaked")) != []


def test_schedule_trace_boots_init_with_tracing_and_shows_both_priorities() -> None:
    trace = scenario("scheduling", "schedule-trace")
    untraced = "\n".join(line for line in TRACED_BOOT if not line.startswith("sched: ")) + "\n"

    assert trace.boot_module is BootModule.INIT
    assert trace.arguments == "trace=schedule"
    assert failures(trace, "\n".join(TRACED_BOOT) + "\n") == []
    assert len(failures(trace, untraced)) == 5
