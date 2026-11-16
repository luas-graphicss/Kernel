import errno
import json
from pathlib import Path

from kernel_tool.qemu.drives import (
    FLUSH_FAILURE_ERRNO,
    Drive,
    FileDrive,
    FlushFailingDrive,
    StalledDrive,
    TracedDrive,
    drive_arguments,
)

IMAGE = Path("/build/scenarios/data.img")
WRITE_LOG = Path("/build/scenarios/data.write-log")
IMAGE_FILE = {"driver": "file", "filename": str(IMAGE)}
DATA_DEVICE = "virtio-blk-device,drive=disk-kernel-data,serial=kernel-data"
STALLED_BYTES = 1 << 20
STALLED_LATENCY_NANOSECONDS = 1_000_000_000


def values_of(arguments: list[str], option: str) -> list[str]:
    return [arguments[index + 1] for index, argument in enumerate(arguments) if argument == option]


def block_nodes(drive: Drive) -> list[dict[str, object]]:
    return [json.loads(node) for node in values_of(drive_arguments(drive), "-blockdev")]


def test_a_file_drive_is_a_raw_virtio_block_device_named_by_its_identity() -> None:
    drive = FileDrive("kernel-data", IMAGE)

    assert block_nodes(drive) == [
        {"driver": "raw", "node-name": "disk-kernel-data", "read-only": False, "file": IMAGE_FILE}
    ]
    assert values_of(drive_arguments(drive), "-device") == [DATA_DEVICE]


def test_a_read_only_drive_is_read_only_at_its_block_node() -> None:
    (node,) = block_nodes(FileDrive("kernel-boot", IMAGE, read_only=True))

    assert node["read-only"] is True
    assert node["file"] == IMAGE_FILE


def test_a_flush_failing_drive_injects_an_io_error_only_into_flushes() -> None:
    (node,) = block_nodes(FlushFailingDrive("kernel-data", IMAGE))

    assert errno.EIO == FLUSH_FAILURE_ERRNO
    assert node == {
        "driver": "raw",
        "node-name": "disk-kernel-data",
        "file": {
            "driver": "blkdebug",
            "image": IMAGE_FILE,
            "inject-error": [
                {"event": "flush_to_os", "iotype": "flush", "errno": FLUSH_FAILURE_ERRNO}
            ],
        },
    }


def test_a_traced_drive_logs_what_reaches_the_image_to_its_own_file() -> None:
    log, traced = block_nodes(TracedDrive("kernel-data", IMAGE, WRITE_LOG))

    assert log == {
        "driver": "file",
        "node-name": "disk-kernel-data-log",
        "filename": str(WRITE_LOG),
    }
    assert traced == {
        "driver": "blklogwrites",
        "node-name": "disk-kernel-data",
        "file": IMAGE_FILE,
        "log": "disk-kernel-data-log",
    }


def test_a_stalled_drive_has_no_backing_file_and_answers_late() -> None:
    drive = StalledDrive("kernel-stalled", STALLED_BYTES, STALLED_LATENCY_NANOSECONDS)

    assert block_nodes(drive) == [
        {
            "driver": "null-co",
            "node-name": "disk-kernel-stalled",
            "size": STALLED_BYTES,
            "latency-ns": STALLED_LATENCY_NANOSECONDS,
            "read-zeroes": True,
        }
    ]


def test_every_drive_ends_with_exactly_one_guest_device() -> None:
    drives: tuple[Drive, ...] = (
        FileDrive("kernel-data", IMAGE),
        FlushFailingDrive("kernel-data", IMAGE),
        TracedDrive("kernel-data", IMAGE, WRITE_LOG),
        StalledDrive("kernel-data", STALLED_BYTES, STALLED_LATENCY_NANOSECONDS),
    )

    for drive in drives:
        arguments = drive_arguments(drive)

        assert arguments[-2:] == ["-device", DATA_DEVICE]
        assert len(values_of(arguments, "-device")) == 1
