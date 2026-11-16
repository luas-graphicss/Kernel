from dataclasses import dataclass
from pathlib import Path

from kernel_tool.build.native import BuildOutputs
from kernel_tool.outcome import InfrastructureError
from kernel_tool.profiles.model import Profile
from kernel_tool.qemu.command import BootRequest, boot_command
from kernel_tool.qemu.session import SessionResult, run_session
from kernel_tool.scenarios.corpus import reference_corpus
from kernel_tool.scenarios.disks import check_data, prepare_machine
from kernel_tool.scenarios.evaluation import check_corpus, check_repeats, check_transcript
from kernel_tool.scenarios.fixtures import boot_module_file, dump_device_tree, edited_device_tree
from kernel_tool.scenarios.model import Deadline, DeviceTreeSource, Image, Scenario
from kernel_tool.storage.volumes import VolumeReport
from kernel_tool.toolchain.fetch import sha256_file
from kernel_tool.toolchain.resolve import Toolchain
from kernel_tool.verification.transcript import read_transcript


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
    transcript: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


def run_scenario(scenario: Scenario, context: SuiteContext) -> ScenarioResult:
    outputs = context.outputs
    kernel = outputs.kernel if scenario.image is Image.KERNEL else outputs.selftest_kernel
    memory_mib = scenario.memory_mib or context.profile.machine.memory_mib
    boot_module = boot_module_file(scenario.boot_module, outputs, context.directory)
    device_tree = _device_tree_file(scenario, context, memory_mib)
    deadline = _deadline_seconds(scenario, context.profile)
    serial_input = scenario.serial_input.encode("utf-8") if scenario.serial_input else None

    failures: list[str] = []
    transcripts: list[tuple[str, ...]] = []
    volume = None
    duration = 0.0
    for _ in range(scenario.repeats):
        machine = prepare_machine(scenario.devices, outputs, context.directory)
        request = BootRequest(
            kernel=kernel,
            memory_mib=memory_mib,
            boot_module=boot_module,
            device_tree=device_tree,
            arguments=scenario.arguments,
            drives=machine.drives,
            entropy=scenario.devices.entropy,
        )
        command = boot_command(context.profile, context.toolchain, request)
        session = run_session(command, deadline, serial_input)
        duration += session.duration_seconds
        transcript = read_transcript(session.transcript)
        transcripts.append(transcript.lines)
        failures.extend(_session_failures(session, deadline))
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


def _session_failures(session: SessionResult, deadline: float) -> list[str]:
    if session.timed_out:
        return [f"the kernel did not shut down within {deadline:g} seconds"]
    if session.exit_code != 0:
        raise InfrastructureError(
            f"the emulator exited with status {session.exit_code}: "
            f"{session.emulator_messages.strip()}"
        )
    return []
