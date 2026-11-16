import re
from dataclasses import dataclass
from pathlib import Path

from kernel_services.filesystem.format.layout import BLOCK_BYTES
from kernel_tool.build.native import BuildOutputs
from kernel_tool.corpus import recipes
from kernel_tool.outcome import CheckError
from kernel_tool.qemu.drives import Drive, FileDrive, FlushFailingDrive, StalledDrive, TracedDrive
from kernel_tool.scenarios.model import DataAttachment, DataCheck, DataDisk, DataSource, Devices
from kernel_tool.storage.volumes import Verdict, VolumeReport, create_image, verify_image
from kernel_tool.toolchain.fetch import sha256_file

BOOT_IDENTITY = "kernel-boot"
DATA_IDENTITY = "kernel-data"
SCRATCH_IDENTITY = "kernel-scratch"
STALLED_IDENTITY = "kernel-stalled"
DATA_BLOCKS = 256
DATA_VOLUME = 0x6B65726E656C
SCRATCH_BYTES = 1 << 20
STALLED_BYTES = 1 << 20
STALLED_LATENCY_NANOSECONDS = 1_000_000_000
DATA_IMAGE = "data.img"
SCRATCH_IMAGE = "scratch.img"
WRITE_LOG = "data.write-log"
VOLUME_REPORT = re.compile(r"^storage: volume generation=(\d+) digest=([0-9a-f]{8})$")


@dataclass(frozen=True, slots=True)
class Machine:
    drives: tuple[Drive, ...]
    data_image: Path | None
    data_sha256: str | None


def write_log_file(directory: Path) -> Path:
    return directory / WRITE_LOG


def prepare_machine(devices: Devices, outputs: BuildOutputs, directory: Path) -> Machine:
    drives: list[Drive] = []
    data_image = None
    if devices.boot:
        drives.append(FileDrive(BOOT_IDENTITY, outputs.boot_image, read_only=True))
    if devices.data is not None:
        data_image = directory / DATA_IMAGE
        _write_data_image(devices.data.source, data_image)
        drives.append(_data_drive(devices.data.attachment, data_image, directory))
    if devices.scratch:
        scratch = directory / SCRATCH_IMAGE
        scratch.write_bytes(bytes(SCRATCH_BYTES))
        drives.append(FileDrive(SCRATCH_IDENTITY, scratch))
    if devices.stalled:
        drives.append(StalledDrive(STALLED_IDENTITY, STALLED_BYTES, STALLED_LATENCY_NANOSECONDS))
    digest = sha256_file(data_image) if data_image is not None else None
    return Machine(tuple(drives), data_image, digest)


def check_data(
    data: DataDisk, machine: Machine, transcript: tuple[str, ...]
) -> tuple[list[str], VolumeReport | None]:
    image = machine.data_image
    if image is None or data.check is DataCheck.UNCHECKED:
        return [], None
    if data.check is DataCheck.UNCHANGED:
        if sha256_file(image) != machine.data_sha256:
            return ["the data image changed although nothing may write to it"], None
        return [], None
    report = verify_image(image.read_bytes())
    if report.verdict is not Verdict.MOUNTABLE:
        return [f"the data image is {report.verdict.value} after the run: {report.reason}"], report
    if data.check is DataCheck.REPORTED and _reported(transcript) != (
        report.generation,
        report.digest,
    ):
        return [
            f"the guest reported {_reported(transcript)} but the image holds "
            f"generation {report.generation} with digest {report.digest}"
        ], report
    return [], report


def _reported(transcript: tuple[str, ...]) -> tuple[int, str] | None:
    reported = None
    for line in transcript:
        match = VOLUME_REPORT.match(line)
        if match is not None:
            reported = (int(match.group(1)), match.group(2))
    return reported


def _write_data_image(source: DataSource, image: Path) -> None:
    match source:
        case DataSource.FORMATTED:
            image.write_bytes(create_image(DATA_BLOCKS, DATA_VOLUME))
        case DataSource.BLANK:
            image.write_bytes(bytes(DATA_BLOCKS * BLOCK_BYTES))
        case DataSource.KEPT:
            if not image.is_file():
                raise CheckError(
                    f"{image} does not exist; run the scenario that writes it before this one"
                )
        case DataSource.UNKNOWN_VERSION | DataSource.DAMAGED_NEWEST_ROOT:
            image.write_bytes(recipes.build(source.value))


def _data_drive(attachment: DataAttachment, image: Path, directory: Path) -> Drive:
    match attachment:
        case DataAttachment.PLAIN:
            return FileDrive(DATA_IDENTITY, image)
        case DataAttachment.READ_ONLY:
            return FileDrive(DATA_IDENTITY, image, read_only=True)
        case DataAttachment.FLUSH_FAILING:
            return FlushFailingDrive(DATA_IDENTITY, image)
        case DataAttachment.TRACED:
            log = write_log_file(directory)
            log.write_bytes(b"")
            return TracedDrive(DATA_IDENTITY, image, log)
