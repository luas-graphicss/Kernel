import re
from pathlib import Path

import pytest

from kernel_tool.commands.test import SUITES
from kernel_tool.network.plan import greeting
from kernel_tool.scenarios.evaluation import check_transcript
from kernel_tool.scenarios.model import (
    SYSTEM_DEVICES,
    BootModule,
    DataSource,
    Deadline,
    Image,
    Scenario,
)
from kernel_tool.scenarios.shell import (
    MANAGER_PROGRAM,
    completed,
    refused_boot_scenario,
    said,
    typed_commands,
)
from kernel_tool.scenarios.system_suites import (
    APPLICATION_LIMIT,
    APPLICATIONS,
    APPLICATIONS_SCENARIO,
    FIRST_BOOT,
    JOURNEY,
    NETWORK_ABSENT,
    REJECTED_CONFIGURATIONS,
    SECOND_BOOT,
    SUPERVISION,
    SUPERVISION_CASES,
    SUPERVISION_SCENARIO,
    SYSTEM_SUITES,
    TEST_PROGRAM_OVERLAY,
)
from kernel_tool.verification.transcript import KernelStatus, read_transcript

REPOSITORY = Path(__file__).resolve().parents[2]
COMMAND_TABLE = REPOSITORY / "src" / "kernel_apps" / "shell" / "commands" / "table.py"
SYSTEM_CONFIGURATION = REPOSITORY / "config" / "system" / "system.conf"
SUPERVISION_PROGRAM = REPOSITORY / "tests/guest/programs/suites/supervision/main.py"
PROMISED = (
    "help",
    "run",
    "ps",
    "kill",
    "wait",
    "mem",
    "ls",
    "cat",
    "mkdir",
    "write",
    "rm",
    "sync",
    "net",
    "ping",
    "shutdown",
)
SHELL_SCENARIOS = (NETWORK_ABSENT, APPLICATIONS_SCENARIO, FIRST_BOOT, SECOND_BOOT)
REFUSED_BOOT = (
    "boot: hart=0",
    f"policy: admitted=init program={MANAGER_PROGRAM} handle=16777216 priority=1",
    "system: manager=started runtime=micropython privilege=user",
    "system: devices serial=1 entropy=1 network=0 block=2",
    "system: configuration=rejected reason=dependency-cycle subject=console",
    "policy: reaped=init reason=exit value=1 live=0 memory-in-use=0",
    "policy: resources=released",
    "kernel: status=failed",
)


def shell_commands() -> tuple[str, ...]:
    source = COMMAND_TABLE.read_text(encoding="utf-8")
    return tuple(re.findall(r'^    \("([a-z]+)", ', source, re.MULTILINE))


def typed(scenario: Scenario) -> list[str]:
    return [step.typed.strip() for step in scenario.steps]


def failures(scenario: Scenario, lines: tuple[str, ...]) -> list[str]:
    return check_transcript(scenario, read_transcript("\n".join(lines) + "\n"))


def test_the_system_suites_are_registered_with_the_test_command() -> None:
    assert set(SYSTEM_SUITES) == {SUPERVISION, APPLICATIONS, JOURNEY}
    for name, scenarios in SYSTEM_SUITES.items():
        assert SUITES[name] is scenarios
        assert len({scenario.name for scenario in scenarios}) == len(scenarios)
    assert SYSTEM_SUITES[JOURNEY] == (FIRST_BOOT, SECOND_BOOT)


def test_the_shell_offers_every_promised_command() -> None:
    assert shell_commands() == PROMISED


def test_the_journey_and_the_applications_type_every_promised_command() -> None:
    used = {command.split(" ")[0] for scenario in SHELL_SCENARIOS for command in typed(scenario)}

    assert used == set(PROMISED)


def test_supervision_expects_the_cases_its_guest_program_declares() -> None:
    source = SUPERVISION_PROGRAM.read_text(encoding="utf-8")

    assert tuple(re.findall(r'^    \("([a-z-]+)", ', source, re.MULTILINE)) == SUPERVISION_CASES
    assert SUPERVISION_SCENARIO.arguments == "init=suites.supervision.main"
    assert SUPERVISION_SCENARIO.boot_module is BootModule.TESTS


def test_each_command_is_typed_after_the_one_before_it_reported_its_status() -> None:
    steps = typed_commands(("ls boot", "run boot/apps/sysinfo.py", "shutdown"))

    assert [step.typed for step in steps] == [
        "ls boot\n",
        "run boot/apps/sysinfo.py\n",
        "shutdown\n",
    ]
    assert steps[0].awaited == r"shell: ready$"
    assert re.search(steps[1].awaited, "shell: command=ls status=ok")
    assert re.search(steps[2].awaited, "kernel> shell: command=run status=failed error=NOT_FOUND")
    assert not re.search(steps[2].awaited, "shell: command=ls status=ok")


def test_what_the_shell_says_is_found_at_the_line_start_or_after_a_prompt() -> None:
    pattern = said(r"wait: application=1 reason=exit value=0")

    assert re.search(pattern, "wait: application=1 reason=exit value=0")
    assert re.search(pattern, "kernel> wait: application=1 reason=exit value=0")
    assert not re.search(pattern, "echo wait: application=1 reason=exit value=0")
    assert not re.search(pattern, "wait: application=1 reason=exit value=01")
    assert re.search(
        completed("rm", "failed error=READ_ONLY"), "shell: command=rm status=failed error=READ_ONLY"
    )


@pytest.mark.parametrize("scenario", SHELL_SCENARIOS, ids=lambda scenario: scenario.name)
def test_shell_scenarios_boot_the_manager_and_end_with_an_ordered_shutdown(
    scenario: Scenario,
) -> None:
    assert scenario.image is Image.KERNEL
    assert scenario.boot_module is BootModule.INIT
    assert scenario.arguments == f"init={MANAGER_PROGRAM}"
    assert scenario.deadline is Deadline.SESSION
    assert scenario.expected_status is KernelStatus.OK
    assert typed(scenario)[-1].startswith("shutdown")
    assert any("shutdown=complete clean=1" in pattern for pattern in scenario.expected_lines)
    for pattern in (*scenario.expected_lines, *scenario.forbidden_lines):
        re.compile(pattern)


def test_the_network_may_be_absent_without_taking_storage_or_the_shell_down() -> None:
    assert NETWORK_ABSENT.network is None
    assert NETWORK_ABSENT.devices == SYSTEM_DEVICES
    assert any("service=network state=degraded" in line for line in NETWORK_ABSENT.expected_lines)
    assert any("service=storage state=ready" in line for line in NETWORK_ABSENT.expected_lines)


def test_rejected_configurations_cover_the_required_kinds_of_document() -> None:
    names = [scenario.name for scenario in REJECTED_CONFIGURATIONS]

    assert names == [
        "configuration-missing",
        "configuration-circular",
        "configuration-excessive",
        "configuration-inconsistent",
    ]
    for scenario in REJECTED_CONFIGURATIONS:
        (entry,) = scenario.boot_overlay
        assert entry.path == "system/config"
        assert scenario.expected_status is KernelStatus.FAILED
        assert not scenario.steps
        if entry.source is not None:
            document = (REPOSITORY / entry.source).read_text(encoding="utf-8")
            assert document != SYSTEM_CONFIGURATION.read_text(encoding="utf-8")


def test_a_rejected_configuration_must_leave_nothing_started() -> None:
    circular = REJECTED_CONFIGURATIONS[1]
    partially_applied = (
        *REFUSED_BOOT[:5],
        "system: service=console state=ready",
        *REFUSED_BOOT[5:],
    )

    assert failures(circular, REFUSED_BOOT) == []
    assert any("forbidden" in failure for failure in failures(circular, partially_applied))


def test_a_refused_boot_scenario_expects_the_failed_exit_of_the_manager() -> None:
    scenario = refused_boot_scenario("sample", (), (r"^system: configuration=rejected ",))

    assert scenario.expected_status is KernelStatus.FAILED
    assert any("value=1" in pattern for pattern in scenario.expected_lines)


def test_applications_run_the_test_programs_from_the_boot_volume() -> None:
    sources = {entry.path: entry.source for entry in TEST_PROGRAM_OVERLAY}

    assert APPLICATIONS_SCENARIO.boot_overlay == TEST_PROGRAM_OVERLAY
    for path, source in sources.items():
        assert source is not None
        assert (REPOSITORY / source).is_file()
        assert path == f"apps/{Path(source).name}"
    started = [command for command in typed(APPLICATIONS_SCENARIO) if command.startswith("run ")]
    assert {command.split(" ")[1].removeprefix("boot/") for command in started} - set(sources) == {
        "apps/missing.py"
    }
    assert typed(APPLICATIONS_SCENARIO).count("run boot/apps/idle.py") == APPLICATION_LIMIT + 1


def test_the_application_limit_is_the_one_the_system_configuration_sets() -> None:
    document = SYSTEM_CONFIGURATION.read_text(encoding="utf-8")
    section = document.split("[access.application]")[1]

    assert re.search(rf"^limit = {APPLICATION_LIMIT}$", section, re.MULTILINE)


def test_the_journey_restarts_under_load_and_checks_its_data_on_the_next_boot() -> None:
    assert FIRST_BOOT.devices.data is not None
    assert SECOND_BOOT.devices.data is not None
    assert FIRST_BOOT.devices.data.source is DataSource.FORMATTED
    assert SECOND_BOOT.devices.data.source is DataSource.KEPT
    assert typed(FIRST_BOOT)[-1] == "shutdown restart"
    assert FIRST_BOOT.expected_lines[-1] == r"^kernel: power=restart$"
    assert typed(SECOND_BOOT)[-1] == "shutdown"
    assert r"^kernel: power=" in SECOND_BOOT.forbidden_lines
    assert any("shutdown=applications stopped=1" in line for line in FIRST_BOOT.expected_lines)


def test_the_journey_fetches_the_greeting_of_the_peer_and_finds_it_after_the_restart() -> None:
    size = len(greeting())
    counted = rf"wordcount: path=data/journey/greeting lines=240 words=1200 bytes={size}$"

    assert FIRST_BOOT.network is not None
    assert {expected.event for expected in FIRST_BOOT.network.reported} == {"greeting", "held"}
    assert counted in FIRST_BOOT.expected_lines
    assert counted in SECOND_BOOT.expected_lines
