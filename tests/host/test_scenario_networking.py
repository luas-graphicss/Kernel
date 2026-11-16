from pathlib import Path

import pytest

from kernel_tool.build.native import BuildOutputs
from kernel_tool.outcome import CheckError
from kernel_tool.scenarios.boot_volume import OVERLAY_IMAGE, boot_volume_file
from kernel_tool.scenarios.model import BootEntry, Reported
from kernel_tool.scenarios.networking import captured_frames, missing_reports
from kernel_tool.scenarios.runner import capture_file
from kernel_tool.storage.boot_image import RELEASE_PATH, read_image, runtime_tag
from kernel_tool.toolchain.lock import load_lock

REPOSITORY = Path(__file__).resolve().parents[2]
RUNTIME = runtime_tag(load_lock(REPOSITORY / "toolchain.lock.toml"))
EVENTS: tuple[dict[str, object], ...] = (
    {"event": "ready", "stack": "Linux 6.8"},
    {"event": "sink", "bytes": 20480, "sha256": "aa", "peer": "10.0.2.15:50000"},
    {"event": "call", "port": 8080, "bytes": 16384, "returned": 16384, "matches": True},
    {"event": "stopped", "captured": 120, "injected": 0},
)


def outputs(directory: Path) -> BuildOutputs:
    return BuildOutputs(
        directory=directory,
        kernel=directory / "kernel.elf",
        selftest_kernel=directory / "kernel-selftest.elf",
        init_program=directory / "user" / "init.elf",
        init_image=directory / "init.img",
        fault_image=directory / "fault.img",
        tests_program=directory / "user" / "tests.elf",
        tests_image=directory / "tests.img",
        boot_image=directory / "boot.img",
    )


def overlaid(tmp_path: Path, *entries: BootEntry) -> dict[str, bytes]:
    image = boot_volume_file(entries, REPOSITORY, outputs(tmp_path), tmp_path)
    return read_image(image.read_bytes(), RUNTIME)


def test_an_event_is_found_when_every_expected_field_agrees() -> None:
    expected = (
        Reported("sink", (("bytes", 20480), ("sha256", "aa"))),
        Reported("call", (("port", 8080), ("matches", True))),
        Reported("stopped"),
    )

    assert missing_reports(expected, EVENTS) == []


def test_an_event_with_another_value_or_another_name_is_missing() -> None:
    expected = (
        Reported("sink", (("bytes", 20480), ("sha256", "bb"))),
        Reported("call", (("port", 8081),)),
        Reported("greeting"),
    )

    missing = missing_reports(expected, EVENTS)

    assert len(missing) == 3
    assert "no sink event" in missing[0]
    assert "'sha256': 'bb'" in missing[0]
    assert "no greeting event" in missing[2]


def test_the_captured_frames_are_the_ones_the_stopped_station_counted() -> None:
    assert captured_frames(EVENTS) == 120
    assert captured_frames(EVENTS[:3]) == 0


def test_each_scenario_keeps_its_capture_among_the_reports(tmp_path: Path) -> None:
    assert capture_file(outputs(tmp_path), "network-cases") == (
        tmp_path / "reports" / "captures" / "network-cases.pcap"
    )


def test_without_an_overlay_a_scenario_boots_the_built_volume(tmp_path: Path) -> None:
    assert boot_volume_file((), REPOSITORY, outputs(tmp_path), tmp_path) == tmp_path / "boot.img"
    assert not (tmp_path / OVERLAY_IMAGE).exists()


def test_an_overlay_adds_replaces_and_removes_files_of_the_boot_volume(tmp_path: Path) -> None:
    files = overlaid(
        tmp_path,
        BootEntry("apps/counter.py", "tests/guest/apps/counter.py"),
        BootEntry("system/config", "tests/guest/configurations/circular.conf"),
        BootEntry("apps/fetch.py", None),
    )

    assert files["apps/counter.py"] == (REPOSITORY / "tests/guest/apps/counter.py").read_bytes()
    assert (
        files["system/config"]
        == (REPOSITORY / "tests/guest/configurations/circular.conf").read_bytes()
    )
    assert "apps/fetch.py" not in files
    assert files["system/license"] == (REPOSITORY / "LICENSE").read_bytes()
    assert RELEASE_PATH in files


def test_removing_a_file_that_is_absent_changes_nothing(tmp_path: Path) -> None:
    files = overlaid(tmp_path, BootEntry("apps/absent.py", None))

    assert "apps/absent.py" not in files
    assert "apps/sysinfo.py" in files


def test_an_overlay_source_that_cannot_be_read_is_reported(tmp_path: Path) -> None:
    with pytest.raises(CheckError, match="cannot read the boot file"):
        overlaid(tmp_path, BootEntry("apps/ghost.py", "tests/guest/apps/ghost.py"))
