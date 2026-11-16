import re

from kernel_tool.scenarios.guest_program import CLEAN_EXIT, FAILED_EXIT, INIT_OPTION
from kernel_tool.scenarios.model import (
    SYSTEM_DEVICES,
    BootEntry,
    BootModule,
    Deadline,
    Devices,
    Image,
    Network,
    Scenario,
    Step,
)
from kernel_tool.verification.transcript import KernelStatus

MANAGER_PROGRAM = "kernel_services.manager.main"
PROMPT = "kernel> "
SHELL_READY = r"shell: ready$"
ADMITTED = rf"^policy: admitted=init program={re.escape(MANAGER_PROGRAM)} handle=\d+ priority=1$"
SYSTEM_FORBIDDEN = (
    r"^trap: ",
    r"^panic: ",
    r"^policy: resources=leaked",
    r"^policy: stopped=deadlock",
)
NOTHING_STARTED = (
    r"system: service=",
    r"system: configuration=accepted",
    r"system: state=",
    r"shell: ready",
)


def said(text: str) -> str:
    return rf"(?:^|{PROMPT}){text}$"


def completed(command: str, outcome: str = "ok") -> str:
    return said(rf"shell: command={command} status={outcome}")


def typed_commands(commands: tuple[str, ...]) -> tuple[Step, ...]:
    steps = []
    awaited = SHELL_READY
    for command in commands:
        steps.append(Step(awaited, command + "\n"))
        name = re.escape(command.split(" ")[0])
        awaited = rf"shell: command={name} status=\S.*$"
    return tuple(steps)


def system_scenario(
    name: str,
    commands: tuple[str, ...],
    reported_lines: tuple[str, ...],
    *,
    devices: Devices = SYSTEM_DEVICES,
    network: Network | None = None,
    boot_overlay: tuple[BootEntry, ...] = (),
    forbidden_lines: tuple[str, ...] = SYSTEM_FORBIDDEN,
    final_lines: tuple[str, ...] = (),
) -> Scenario:
    return Scenario(
        name=name,
        image=Image.KERNEL,
        boot_module=BootModule.INIT,
        expected_status=KernelStatus.OK,
        expected_lines=(ADMITTED, *reported_lines, *CLEAN_EXIT, *final_lines),
        forbidden_lines=forbidden_lines,
        arguments=INIT_OPTION + MANAGER_PROGRAM,
        deadline=Deadline.SESSION,
        devices=devices,
        steps=typed_commands(commands),
        network=network,
        boot_overlay=boot_overlay,
    )


def refused_boot_scenario(
    name: str, boot_overlay: tuple[BootEntry, ...], reported_lines: tuple[str, ...]
) -> Scenario:
    return Scenario(
        name=name,
        image=Image.KERNEL,
        boot_module=BootModule.INIT,
        expected_status=KernelStatus.FAILED,
        expected_lines=(ADMITTED, *reported_lines, *FAILED_EXIT),
        forbidden_lines=(*SYSTEM_FORBIDDEN, *NOTHING_STARTED),
        arguments=INIT_OPTION + MANAGER_PROGRAM,
        devices=SYSTEM_DEVICES,
        boot_overlay=boot_overlay,
    )
