from pathlib import Path

import pytest

from kernel_services.filesystem.format.layout import BLOCK_BYTES, KIND_FILE, SUPERBLOCK_SLOTS
from kernel_services.filesystem.volume import Volume
from kernel_tool.build.native import BuildOutputs
from kernel_tool.outcome import CheckError
from kernel_tool.qemu.drives import FileDrive, FlushFailingDrive, StalledDrive, TracedDrive
from kernel_tool.scenarios.disks import (
    BOOT_IDENTITY,
    DATA_BLOCKS,
    DATA_IDENTITY,
    DATA_IMAGE,
    SCRATCH_BYTES,
    SCRATCH_IDENTITY,
    SCRATCH_IMAGE,
    STALLED_BYTES,
    STALLED_IDENTITY,
    STALLED_LATENCY_NANOSECONDS,
    Machine,
    check_data,
    prepare_machine,
    write_log_file,
)
from kernel_tool.scenarios.model import (
    NO_DEVICES,
    DataAttachment,
    DataCheck,
    DataDisk,
    DataSource,
    Devices,
)
from kernel_tool.storage.image_store import ImageStore
from kernel_tool.storage.volumes import Verdict, verify_image

UNCHANGED_FAILURE = "the data image changed although nothing may write to it"


def outputs(directory: Path) -> BuildOutputs:
    return BuildOutputs(
        directory=directory,
        kernel=directory / "kernel.elf",
        selftest_kernel=directory / "kernel-selftest.elf",
        init_program=directory / "init.elf",
        init_image=directory / "init.img",
        fault_image=directory / "fault.img",
        tests_program=directory / "tests.elf",
        tests_image=directory / "tests.img",
        boot_image=directory / "boot.img",
    )


def prepare(devices: Devices, directory: Path) -> Machine:
    return prepare_machine(devices, outputs(directory), directory)


def prepare_data(data: DataDisk, directory: Path) -> Machine:
    return prepare(Devices(data=data), directory)


def data_image(machine: Machine) -> Path:
    assert machine.data_image is not None
    return machine.data_image


def write_as_a_guest(image: Path) -> tuple[int | None, str | None]:
    store = ImageStore(image.read_bytes())
    volume = Volume(store)
    volume.write(volume.create(volume.root(), b"file.bin", KIND_FILE), 0, b"content")
    volume.sync()
    image.write_bytes(bytes(store.content))
    report = verify_image(bytes(store.content))
    return report.generation, report.digest


def test_a_machine_without_devices_has_no_drives_and_writes_nothing(tmp_path: Path) -> None:
    machine = prepare(NO_DEVICES, tmp_path)

    assert machine == Machine((), None, None)
    assert list(tmp_path.iterdir()) == []


def test_drives_are_attached_in_a_fixed_order(tmp_path: Path) -> None:
    devices = Devices(boot=True, data=DataDisk(), scratch=True, stalled=True)

    machine = prepare(devices, tmp_path)

    assert machine.drives == (
        FileDrive(BOOT_IDENTITY, tmp_path / "boot.img", read_only=True),
        FileDrive(DATA_IDENTITY, tmp_path / DATA_IMAGE),
        FileDrive(SCRATCH_IDENTITY, tmp_path / SCRATCH_IMAGE),
        StalledDrive(STALLED_IDENTITY, STALLED_BYTES, STALLED_LATENCY_NANOSECONDS),
    )
    assert (tmp_path / SCRATCH_IMAGE).read_bytes() == bytes(SCRATCH_BYTES)


def test_a_formatted_volume_is_created_again_for_every_boot(tmp_path: Path) -> None:
    machine = prepare_data(DataDisk(), tmp_path)
    image = data_image(machine)
    created = image.read_bytes()
    report = verify_image(created)

    image.write_bytes(b"left by an earlier boot")
    again = prepare_data(DataDisk(), tmp_path)

    assert (report.verdict, report.generation, report.total_blocks) == (
        Verdict.MOUNTABLE,
        1,
        DATA_BLOCKS,
    )
    assert data_image(again).read_bytes() == created
    assert again.data_sha256 == machine.data_sha256


def test_a_kept_volume_must_have_been_written_by_an_earlier_scenario(tmp_path: Path) -> None:
    kept = DataDisk(DataSource.KEPT)

    with pytest.raises(CheckError, match="run the scenario that writes it"):
        prepare_data(kept, tmp_path)
    image = data_image(prepare_data(DataDisk(), tmp_path))
    write_as_a_guest(image)
    written = image.read_bytes()

    assert data_image(prepare_data(kept, tmp_path)).read_bytes() == written


@pytest.mark.parametrize(
    ("source", "verdict"),
    [
        (DataSource.BLANK, Verdict.CORRUPTED),
        (DataSource.UNKNOWN_VERSION, Verdict.UNSUPPORTED),
        (DataSource.DAMAGED_NEWEST_ROOT, Verdict.READ_ONLY),
    ],
)
def test_untrusted_sources_are_volumes_the_guest_must_refuse_or_protect(
    tmp_path: Path, source: DataSource, verdict: Verdict
) -> None:
    image = data_image(prepare_data(DataDisk(source), tmp_path))

    assert verify_image(image.read_bytes()).verdict is verdict


def test_the_attachment_chooses_how_the_image_reaches_the_guest(tmp_path: Path) -> None:
    image = tmp_path / DATA_IMAGE
    log = write_log_file(tmp_path)
    log.write_bytes(b"left by an earlier boot")

    def drive(attachment: DataAttachment) -> object:
        return prepare_data(DataDisk(attachment=attachment), tmp_path).drives[0]

    assert drive(DataAttachment.PLAIN) == FileDrive(DATA_IDENTITY, image)
    assert drive(DataAttachment.READ_ONLY) == FileDrive(DATA_IDENTITY, image, read_only=True)
    assert drive(DataAttachment.FLUSH_FAILING) == FlushFailingDrive(DATA_IDENTITY, image)
    assert log.read_bytes() == b"left by an earlier boot"
    assert drive(DataAttachment.TRACED) == TracedDrive(DATA_IDENTITY, image, log)
    assert log.read_bytes() == b""


def test_an_unchecked_volume_is_not_read_after_the_run(tmp_path: Path) -> None:
    data = DataDisk(check=DataCheck.UNCHECKED)
    machine = prepare_data(data, tmp_path)
    data_image(machine).write_bytes(b"not a volume")

    assert check_data(data, machine, ()) == ([], None)
    assert check_data(data, prepare(NO_DEVICES, tmp_path), ()) == ([], None)


def test_a_volume_that_must_stay_unchanged_is_compared_with_its_hash(tmp_path: Path) -> None:
    data = DataDisk(check=DataCheck.UNCHANGED)
    machine = prepare_data(data, tmp_path)

    assert check_data(data, machine, ()) == ([], None)
    write_as_a_guest(data_image(machine))
    assert check_data(data, machine, ()) == ([UNCHANGED_FAILURE], None)


def test_a_consistent_volume_must_still_mount_read_write_after_the_run(tmp_path: Path) -> None:
    data = DataDisk(check=DataCheck.CONSISTENT)
    machine = prepare_data(data, tmp_path)
    image = data_image(machine)
    write_as_a_guest(image)

    failures, report = check_data(data, machine, ())
    assert failures == []
    assert report is not None
    assert report.verdict is Verdict.MOUNTABLE

    damaged = bytearray(image.read_bytes())
    damaged[: SUPERBLOCK_SLOTS * BLOCK_BYTES] = bytes(SUPERBLOCK_SLOTS * BLOCK_BYTES)
    image.write_bytes(damaged)
    failures, report = check_data(data, machine, ())
    assert len(failures) == 1
    assert "is corrupted after the run" in failures[0]
    assert report is not None
    assert report.verdict is Verdict.CORRUPTED


def test_a_reported_volume_must_match_the_last_report_of_the_guest(tmp_path: Path) -> None:
    data = DataDisk(check=DataCheck.REPORTED)
    machine = prepare_data(data, tmp_path)
    generation, digest = write_as_a_guest(data_image(machine))
    older = "storage: volume generation=1 digest=00000000"
    newest = f"storage: volume generation={generation} digest={digest}"

    assert check_data(data, machine, (older, newest))[0] == []
    outdated, _report = check_data(data, machine, (newest, older))
    silent, _report = check_data(data, machine, ("storage: tree=written result=ok",))
    assert len(outdated) == 1
    assert "the guest reported (1, '00000000')" in outdated[0]
    assert len(silent) == 1
    assert "the guest reported None" in silent[0]
