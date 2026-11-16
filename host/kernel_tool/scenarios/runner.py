from dataclasses import dataclass, replace
from pathlib import Path

from kernel_tool.build.native import BuildOutputs
from kernel_tool.outcome import InfrastructureError
from kernel_tool.profiles.model import Profile
from kernel_tool.qemu.command import BootRequest, boot_command
from kernel_tool.qemu.session import SessionResult
from kernel_tool.scenarios.boot_volume import boot_volume_file
from kernel_tool.scenarios.corpus import reference_corpus
from kernel_tool.scenarios.disks import check_data, prepare_machine
from kernel_tool.scenarios.evaluation import check_corpus, check_repeats, check_transcript
from kernel_tool.scenarios.fixtures import boot_module_file, dump_device_tree, edited_device_tree
from kernel_tool.scenarios.model import Deadline, DeviceTreeSource, Image, Scenario
from kernel_tool.scenarios.networking import NetworkEvidence
from kernel_tool.scenarios.session import hold_session
from kernel_tool.storage.volumes import VolumeReport
from kernel_tool.toolchain.fetch import sha256_file
from kernel_tool.toolchain.resolve import Toolchain
from kernel_tool.verification.transcript import read_transcript

REPORTS_DIRECTORY = "reports"
CAPTURES_DIRECTORY = "captures"
STATIONS_DIRECTORY = "network"
CAPTURE_SUFFIX = ".pcap"


@dataclass(frozen=True, slots=True)
class SuiteContext:
    root: Path
    profile: Profile
    toolchain: Toolchain
    outputs: BuildOutputs
    directory: Path


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    failures: tuple[str, ...]
    runs: int
    duration_seconds: float
    image: str
    image_sha256: str
    boot_module_sha256: str | None
    volume: VolumeReport | None
    network: NetworkEvidence | None
    transcript: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def capture_file(outputs: BuildOutputs, scenario: str) -> Path:
    return outputs.directory / REPORTS_DIRECTORY / CAPTURES_DIRECTORY / (scenario + CAPTURE_SUFFIX)


def run_scenario(scenario: Scenario, context: SuiteContext) -> ScenarioResult:
    outputs = context.outputs
    kernel = outputs.kernel if scenario.image is Image.KERNEL else outputs.selftest_kernel
    memory_mib = scenario.memory_mib or context.profile.machine.memory_mib
    boot_module = boot_module_file(scenario.boot_module, outputs, context.directory)
    device_tree = _device_tree_file(scenario, context, memory_mib)
    boot_volume = boot_volume_file(scenario.boot_overlay, context.root, outputs, context.directory)
    deadline = _deadline_seconds(scenario, context.profile)

    failures: list[str] = []
    transcripts: list[tuple[str, ...]] = []
    volume = None
    network = None
    duration = 0.0
    for _ in range(scenario.repeats):
        machine = prepare_machine(scenario.devices, boot_volume, context.directory)
        request = BootRequest(
            kernel=kernel,
            memory_mib=memory_mib,
            boot_module=boot_module,
            device_tree=device_tree,
            arguments=scenario.arguments,
            drives=machine.drives,
            entropy=scenario.devices.entropy,
        )

        def build_command(
            network_arguments: tuple[str, ...], request: BootRequest = request
        ) -> list[str]:
            attached = replace(request, network=network_arguments)
            return boot_command(context.profile, context.toolchain, attached)

        boot = hold_session(
            scenario,
            build_command,
            deadline,
            context.directory / STATIONS_DIRECTORY / scenario.name,
            capture_file(outputs, scenario.name),
        )
        duration += boot.session.duration_seconds
        network = boot.network
        transcript = read_transcript(boot.session.transcript)
        transcripts.append(transcript.lines)
        failures.extend(_session_failures(boot.session, deadline))
        failures.extend(boot.failures)
        if not failures:
            failures.extend(check_transcript(scenario, transcript))
        if not failures and scenario.devices.data is not None:
            data_failures, volume = check_data(scenario.devices.data, machine, transcript.lines)
            failures.extend(data_failures)
        if failures:
            break
    if not failures:
        failures.extend(check_repeats(transcripts))
    if not failures and scenario.compares_corpus:
        failures.extend(check_corpus(transcripts[-1], reference_corpus(context.root)))

    return ScenarioResult(
        name=scenario.name,
        failures=tuple(failures),
        runs=len(transcripts),
        duration_seconds=round(duration, 3),
        image=kernel.name,
        image_sha256=sha256_file(kernel),
        boot_module_sha256=sha256_file(boot_module) if boot_module else None,
        volume=volume,
        network=network,
        transcript=transcripts[-1],
    )


def _device_tree_file(scenario: Scenario, context: SuiteContext, memory_mib: int) -> Path | None:
    if scenario.device_tree is DeviceTreeSource.GENERATED:
        return None
    generated = dump_device_tree(context.profile, context.toolchain, memory_mib, context.directory)
    edited = context.directory / f"{scenario.device_tree.value}.dtb"
    edited.write_bytes(edited_device_tree(scenario.device_tree, generated))
    return edited


def _deadline_seconds(scenario: Scenario, profile: Profile) -> float:
    match scenario.deadline:
        case Deadline.BOOT:
            return float(profile.deadlines.boot_seconds)
        case Deadline.SELFTEST:
            return float(profile.deadlines.selftest_seconds)
        case Deadline.SOAK:
            return float(profile.deadlines.soak_seconds)
        case Deadline.SESSION:
            return float(profile.deadlines.session_seconds)


def _session_failures(session: SessionResult, deadline: float) -> list[str]:
    if session.timed_out:
        return [f"the kernel did not shut down within {deadline:g} seconds"]
    if session.exit_code != 0:
        raise InfrastructureError(
            f"the emulator exited with status {session.exit_code}: "
            f"{session.emulator_messages.strip()}"
        )
    return []
