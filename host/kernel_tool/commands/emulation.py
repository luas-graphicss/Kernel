import argparse
import logging
from contextlib import ExitStack
from pathlib import Path

from kernel_tool.build.native import build_outputs, require_artifacts
from kernel_tool.commands.options import (
    CommandRegistry,
    add_profile_option,
    load_toolchain,
    selected_profile,
)
from kernel_tool.network.link import StationLink
from kernel_tool.network.plan import NetworkPlan
from kernel_tool.outcome import CheckError, ExitCode, InfrastructureError
from kernel_tool.qemu.command import BootRequest, boot_command
from kernel_tool.qemu.console import run_attached
from kernel_tool.qemu.drives import Drive, FileDrive
from kernel_tool.qemu.session import SessionResult
from kernel_tool.scenarios.disks import BOOT_IDENTITY, DATA_BLOCKS, DATA_IDENTITY, DATA_VOLUME
from kernel_tool.scenarios.guest_program import INIT_OPTION
from kernel_tool.scenarios.shell import MANAGER_PROGRAM
from kernel_tool.storage.volumes import create_image
from kernel_tool.verification.transcript import KernelStatus, read_transcript
from kernel_tool.workspace import Workspace

SYSTEM_DIRECTORY = "system"
DATA_IMAGE = "data.img"
NETWORK_DIRECTORY = "network"
RESTART_REQUESTED = "kernel: power=restart"

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    run = commands.add_parser(
        "run", help="boot the system in QEMU with its console on this terminal"
    )
    add_profile_option(run)
    run.add_argument(
        "--deadline",
        type=float,
        default=None,
        help="seconds before a boot counts as failed (default: no limit)",
    )
    run.add_argument(
        "--without-network",
        action="store_true",
        help="boot without the network device and its isolated peer",
    )
    run.set_defaults(handler=run_system)


def run_system(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    profile = selected_profile(workspace, options)
    toolchain = load_toolchain(workspace)
    outputs = build_outputs(workspace, profile)
    require_artifacts(outputs)
    directory = outputs.directory / SYSTEM_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    drives = system_drives(outputs.boot_image, directory)
    deadline: float | None = options.deadline
    without_network: bool = options.without_network

    with ExitStack() as stack:
        link = None if without_network else attach_network(stack, directory)
        while True:
            request = BootRequest(
                kernel=outputs.kernel,
                memory_mib=profile.machine.memory_mib,
                boot_module=outputs.init_image,
                arguments=INIT_OPTION + MANAGER_PROGRAM,
                drives=drives,
                entropy=True,
                network=tuple(link.emulator_arguments()) if link is not None else (),
            )
            try:
                result = run_attached(boot_command(profile, toolchain, request), deadline)
            except KeyboardInterrupt:
                raise CheckError("the session was interrupted") from None
            if not asks_restart(result, deadline):
                return ExitCode.OK
            logger.info("the system asked for a restart; booting it again")


def system_drives(boot_image: Path, directory: Path) -> tuple[Drive, ...]:
    data_image = directory / DATA_IMAGE
    if not data_image.is_file():
        data_image.write_bytes(create_image(DATA_BLOCKS, DATA_VOLUME))
        logger.info("created the data volume %s", data_image)
    return (
        FileDrive(BOOT_IDENTITY, boot_image, read_only=True),
        FileDrive(DATA_IDENTITY, data_image),
    )


def attach_network(stack: ExitStack, directory: Path) -> StationLink | None:
    try:
        return stack.enter_context(StationLink(directory / NETWORK_DIRECTORY, NetworkPlan()))
    except InfrastructureError as error:
        logger.warning("booting without a network: %s", error)
        return None


def asks_restart(result: SessionResult, deadline: float | None) -> bool:
    if result.timed_out:
        raise CheckError(f"the system did not stop within {deadline:g} seconds")
    if result.exit_code != 0:
        raise InfrastructureError(
            f"the emulator exited with status {result.exit_code}: "
            f"{result.emulator_messages.strip()}"
        )
    transcript = read_transcript(result.transcript)
    if transcript.status is not KernelStatus.OK:
        raise CheckError(f"the kernel reported status {transcript.status.value}")
    return RESTART_REQUESTED in transcript.lines
