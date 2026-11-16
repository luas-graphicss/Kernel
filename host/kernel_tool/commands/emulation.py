import argparse
import sys

from kernel_tool.build.native import build_outputs
from kernel_tool.commands.options import (
    CommandRegistry,
    add_profile_option,
    load_toolchain,
    selected_profile,
)
from kernel_tool.outcome import CheckError, ExitCode, InfrastructureError
from kernel_tool.qemu.command import BootRequest, boot_command
from kernel_tool.qemu.session import run_session
from kernel_tool.verification.transcript import KernelStatus, read_transcript
from kernel_tool.workspace import Workspace


def register(commands: CommandRegistry) -> None:
    run = commands.add_parser(
        "run", help="boot the built image in QEMU and print the serial output"
    )
    add_profile_option(run)
    run.add_argument(
        "--deadline",
        type=float,
        default=None,
        help="seconds before the boot counts as failed (default: the profile deadline)",
    )
    run.set_defaults(handler=run_image)


def run_image(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    profile = selected_profile(workspace, options)
    toolchain = load_toolchain(workspace)
    outputs = build_outputs(workspace, profile)
    if not outputs.kernel.is_file():
        raise CheckError(f"{outputs.kernel} does not exist; run kernel-tool build first")

    requested_deadline: float | None = options.deadline
    deadline = requested_deadline or float(profile.deadlines.boot_seconds)
    request = BootRequest(kernel=outputs.kernel, memory_mib=profile.machine.memory_mib)
    result = run_session(boot_command(profile, toolchain, request), deadline)
    sys.stdout.write(result.transcript)

    if result.timed_out:
        raise CheckError(f"the kernel did not shut down within {deadline:g} seconds")
    if result.exit_code != 0:
        raise InfrastructureError(
            f"the emulator exited with status {result.exit_code}: "
            f"{result.emulator_messages.strip()}"
        )
    status = read_transcript(result.transcript).status
    if status is not KernelStatus.OK:
        raise CheckError(f"the kernel reported status {status.value}")
    return ExitCode.OK
