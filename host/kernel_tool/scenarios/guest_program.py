import re

from kernel_tool.scenarios.model import BootModule, Deadline, Devices, Image, Scenario
from kernel_tool.verification.transcript import KernelStatus

INIT_OPTION = "init="
FORBIDDEN_LINES = (
    r"^trap: ",
    r"^panic: ",
    r"^Traceback ",
    r"^test: .* result=(?!ok$)",
    r"^policy: resources=leaked",
    r"^policy: stopped=deadlock",
)
CLEAN_EXIT = (
    r"^policy: reaped=init reason=exit value=0 live=0 memory-in-use=0$",
    r"^policy: resources=released$",
)
FAILED_EXIT = (
    r"^policy: reaped=init reason=exit value=1 live=0 memory-in-use=0$",
    r"^policy: resources=released$",
)


def case_lines(suite: str, cases: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(rf"^test: suite={suite} case={case} checks=[1-9]\d* result=ok$" for case in cases)


def program_scenario(
    name: str,
    boot_module: BootModule,
    arguments: str,
    reported_lines: tuple[str, ...],
    deadline: Deadline = Deadline.BOOT,
) -> Scenario:
    return Scenario(
        name=name,
        image=Image.KERNEL,
        boot_module=boot_module,
        expected_status=KernelStatus.OK,
        expected_lines=(*reported_lines, *CLEAN_EXIT),
        forbidden_lines=FORBIDDEN_LINES,
        arguments=arguments,
        deadline=deadline,
    )


def tests_image_scenario(
    name: str, program: str, reported_lines: tuple[str, ...], deadline: Deadline = Deadline.BOOT
) -> Scenario:
    admitted = rf"^policy: admitted=init program={re.escape(program)} handle=\d+ priority=1$"
    return program_scenario(
        name, BootModule.TESTS, INIT_OPTION + program, (admitted, *reported_lines), deadline
    )


def init_scenario(
    name: str,
    devices: Devices,
    reported_lines: tuple[str, ...],
    expected_status: KernelStatus = KernelStatus.OK,
) -> Scenario:
    exit_lines = CLEAN_EXIT if expected_status is KernelStatus.OK else FAILED_EXIT
    return Scenario(
        name=name,
        image=Image.KERNEL,
        boot_module=BootModule.INIT,
        expected_status=expected_status,
        expected_lines=(*reported_lines, *exit_lines),
        forbidden_lines=FORBIDDEN_LINES,
        devices=devices,
    )
