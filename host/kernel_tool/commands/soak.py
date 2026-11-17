import argparse
import logging
import sys
from pathlib import Path

from kernel_tool.build.native import build_outputs, require_artifacts
from kernel_tool.commands.options import (
    CommandRegistry,
    add_profile_option,
    load_toolchain,
    selected_profile,
)
from kernel_tool.network.plan import NetworkPlan
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.qemu.command import BootRequest, boot_command
from kernel_tool.qualification.evidence import (
    SOAK,
    artifact_identity,
    evidence_file,
    write_evidence,
)
from kernel_tool.qualification.soak import (
    FREE_FRAMES,
    WARM_UP_ROUNDS,
    RoundSample,
    analyze,
    run_session,
    soak_document,
)
from kernel_tool.qualification.trends import Trend
from kernel_tool.scenarios.boot_volume import boot_volume_file
from kernel_tool.scenarios.disks import prepare_machine
from kernel_tool.scenarios.guest_program import INIT_OPTION
from kernel_tool.scenarios.measurement_suites import COLLECTOR_TRACE
from kernel_tool.scenarios.model import SYSTEM_DEVICES, Network
from kernel_tool.scenarios.networking import attached_network
from kernel_tool.scenarios.release_suites import test_application
from kernel_tool.scenarios.shell import MANAGER_PROGRAM
from kernel_tool.storage.volumes import Verdict, verify_image
from kernel_tool.workspace import Workspace

SOAK_DIRECTORY = "soak"
NETWORK_DIRECTORY = "network"
CAPTURE_FILE = "soak.pcap"
LOG_FILE = "soak.log"
SECONDS_PER_HOUR = 3600
PROGRESS_INTERVAL = 25
LOAD_APPLICATIONS = ("hog.py", "spin.py", "chatter.py", "pulse.py")

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    soak = commands.add_parser(
        "soak",
        help="keep one boot under processes, files, network and memory pressure for hours",
    )
    add_profile_option(soak)
    soak.add_argument(
        "--hours", type=positive_hours, required=True, help="hours the single boot stays loaded"
    )
    soak.add_argument(
        "--without-network",
        action="store_true",
        help="leave the network out of the load; such a run does not satisfy the release gate",
    )
    soak.set_defaults(handler=run_soak)


def positive_hours(text: str) -> float:
    hours = float(text)
    if hours <= 0:
        raise argparse.ArgumentTypeError("the duration must be greater than zero")
    return hours


def run_soak(workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    hours: float = options.hours
    without_network: bool = options.without_network
    profile = selected_profile(workspace, options)
    toolchain = load_toolchain(workspace)
    outputs = build_outputs(workspace, profile)
    require_artifacts(outputs)
    directory = outputs.directory / SOAK_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    overlay = tuple(test_application(name) for name in LOAD_APPLICATIONS)
    machine = prepare_machine(
        SYSTEM_DEVICES, boot_volume_file(overlay, workspace.root, outputs, directory), directory
    )

    network = None if without_network else Network(NetworkPlan())
    with attached_network(
        network, directory / NETWORK_DIRECTORY, directory / CAPTURE_FILE
    ) as station:
        request = BootRequest(
            kernel=outputs.kernel,
            memory_mib=profile.machine.memory_mib,
            boot_module=outputs.init_image,
            arguments=INIT_OPTION + MANAGER_PROGRAM + COLLECTOR_TRACE,
            drives=machine.drives,
            entropy=True,
            network=station.arguments if station is not None else (),
        )
        session = run_session(
            boot_command(profile, toolchain, request),
            hours * SECONDS_PER_HOUR,
            directory / LOG_FILE,
            station is not None,
            log_progress,
        )
        if station is not None:
            station.finish()

    trends = analyze(session.samples)
    failures = [*session.failures, *trend_failures(trends), *volume_failures(machine.data_image)]
    document = soak_document(session, trends, failures) | {
        "profile": profile.name,
        "artifacts": artifact_identity(outputs),
        "requested_hours": hours,
        "network": not without_network,
        "log": str(directory / LOG_FILE),
    }
    report = evidence_file(outputs, SOAK)
    write_evidence(report, document)
    sys.stdout.write(
        f"soak rounds={len(session.samples)} seconds={session.seconds:.0f} "
        f"network={int(not without_network)} failures={len(failures)}\n"
    )
    if failures:
        raise CheckError("the soak failed:\n" + "\n".join(failures) + f"\nsee {report}")
    if len(session.samples) <= WARM_UP_ROUNDS:
        raise CheckError(
            f"the soak ended within its warm-up of {WARM_UP_ROUNDS} rounds; nothing was observed"
        )
    logger.info("the soak passed; report written to %s", report)
    return ExitCode.OK


def trend_failures(trends: dict[str, Trend]) -> list[str]:
    return [
        f"{name} kept worsening after the warm-up: median {trend.earlier_median:g} -> "
        f"{trend.later_median:g}, extreme {trend.earlier_extreme} -> {trend.later_extreme}"
        for name, trend in trends.items()
        if trend.persistent
    ]


def volume_failures(image: Path | None) -> list[str]:
    if image is None:
        return ["the soak ran without a data volume"]
    report = verify_image(image.read_bytes())
    if report.verdict is not Verdict.MOUNTABLE:
        return [f"the data volume is {report.verdict.value} after the soak: {report.reason}"]
    return []


def log_progress(sample: RoundSample) -> None:
    if sample.number % PROGRESS_INTERVAL == 0:
        logger.info("round %d: %s=%s", sample.number, FREE_FRAMES, sample.counters.get(FREE_FRAMES))
