import re
from dataclasses import replace

import pytest

from kernel_tool.scenarios import disks
from kernel_tool.scenarios.evaluation import check_transcript
from kernel_tool.scenarios.guest_suites import GUEST_SUITES, TYPED_LINES, VOLUME_REPORT
from kernel_tool.scenarios.model import (
    NO_DEVICES,
    SYSTEM_DEVICES,
    BootModule,
    DataAttachment,
    DataCheck,
    DataDisk,
    DataSource,
    Devices,
    Scenario,
)
from kernel_tool.verification.transcript import KernelStatus, read_transcript

PROTECTED_CORE_SUITES = ("memory", "processes", "capabilities", "ipc", "scheduling")
UNTRUSTED_VOLUMES = {
    "read-only-device": DataDisk(DataSource.KEPT, DataAttachment.READ_ONLY, DataCheck.UNCHANGED),
    "unformatted-device": DataDisk(DataSource.BLANK, DataAttachment.PLAIN, DataCheck.UNCHANGED),
    "unknown-format-version": DataDisk(
        DataSource.UNKNOWN_VERSION, DataAttachment.PLAIN, DataCheck.UNCHANGED
    ),
    "damaged-newest-root": DataDisk(
        DataSource.DAMAGED_NEWEST_ROOT, DataAttachment.PLAIN, DataCheck.UNCHANGED
    ),
}
FAILED_FLUSH = (
    "boot: hart=0",
    "init: mount=data mode=read-write reason=clean",
    "init: data=failed error=IO_ERROR",
    "filesystem: stop=unsynced error=IO_ERROR",
    "policy: reaped=init reason=exit value=1 live=0 memory-in-use=0",
    "policy: resources=released",
    "kernel: status=failed",
)
REPORTED_VOLUME = "storage: volume generation=7 digest=0badc0de"
MALFORMED_REPORTS = (
    "storage: volume generation=7 digest=0BADC0DE",
    "storage: volume generation=-1 digest=0badc0de",
    "storage: volume generation=7 digest=0badc0d",
    REPORTED_VOLUME + " ",
)


def scenario(suite: str, name: str) -> Scenario:
    return next(candidate for candidate in GUEST_SUITES[suite] if candidate.name == name)


def failures(candidate: Scenario, lines: tuple[str, ...]) -> list[str]:
    return check_transcript(candidate, read_transcript("\n".join(lines) + "\n"))


def test_suites_of_the_protected_core_boot_without_devices() -> None:
    for suite in PROTECTED_CORE_SUITES:
        assert all(candidate.devices == NO_DEVICES for candidate in GUEST_SUITES[suite])


def test_driver_programs_get_a_scratch_disk_and_entropy_but_no_system_volume() -> None:
    for name in ("cases", "services"):
        assert scenario("devices", name).devices == Devices(scratch=True, entropy=True)


def test_console_service_reads_typed_lines_that_need_editing() -> None:
    services = scenario("devices", "services")

    assert services.serial_input == TYPED_LINES
    assert "\r" in TYPED_LINES
    assert "\x7f" in TYPED_LINES
    assert TYPED_LINES.endswith("\n")
    assert r"^console: written by a client$" in services.expected_lines


def test_a_machine_without_entropy_boots_and_reports_the_source_as_unavailable() -> None:
    without = scenario("devices", "without-entropy")

    assert without.boot_module is BootModule.INIT
    assert without.devices == replace(SYSTEM_DEVICES, entropy=False)
    assert without.expected_status is KernelStatus.OK
    assert r"^init: entropy=unavailable$" in without.expected_lines


def test_file_suites_boot_with_the_boot_image_a_fresh_volume_and_entropy() -> None:
    fresh_volume = DataDisk(DataSource.FORMATTED, DataAttachment.PLAIN, DataCheck.CONSISTENT)

    assert Devices(boot=True, data=fresh_volume, entropy=True) == SYSTEM_DEVICES
    for suite in ("vfs", "storage"):
        assert scenario(suite, "cases").devices == SYSTEM_DEVICES


def test_persistence_is_read_back_by_a_second_boot_of_the_kept_image() -> None:
    names = [candidate.name for candidate in GUEST_SUITES["storage"]]
    written = scenario("storage", "persistence-write")
    verified = scenario("storage", "persistence-verify")

    assert names.index("persistence-write") < names.index("persistence-verify")
    assert written.arguments == "init=suites.storage.writer"
    assert verified.arguments == "init=suites.storage.reader"
    assert written.devices.data == DataDisk(
        DataSource.FORMATTED, DataAttachment.PLAIN, DataCheck.REPORTED
    )
    assert verified.devices.data == DataDisk(
        DataSource.KEPT, DataAttachment.PLAIN, DataCheck.REPORTED
    )
    assert VOLUME_REPORT in written.expected_lines
    assert VOLUME_REPORT in verified.expected_lines


@pytest.mark.parametrize("name", sorted(UNTRUSTED_VOLUMES))
def test_a_volume_that_cannot_be_trusted_must_end_the_boot_unchanged(name: str) -> None:
    candidate = scenario("storage", name)

    assert candidate.boot_module is BootModule.INIT
    assert candidate.devices.data == UNTRUSTED_VOLUMES[name]
    assert candidate.expected_status is KernelStatus.OK
    assert not any("mode=read-write" in pattern for pattern in candidate.expected_lines)


def test_a_failing_flush_fails_the_boot_instead_of_reporting_success() -> None:
    failing = scenario("storage", "flush-failure")
    succeeded = tuple(line.replace("status=failed", "status=ok") for line in FAILED_FLUSH)
    unreported = tuple(line for line in FAILED_FLUSH if not line.startswith("filesystem: "))

    assert failing.devices.data == DataDisk(
        DataSource.FORMATTED, DataAttachment.FLUSH_FAILING, DataCheck.CONSISTENT
    )
    assert failures(failing, FAILED_FLUSH) == []
    assert failures(failing, succeeded) == ["kernel status is ok, expected failed"]
    assert len(failures(failing, unreported)) == 1


def test_scenarios_and_the_image_check_read_the_same_volume_report() -> None:
    match = disks.VOLUME_REPORT.match(REPORTED_VOLUME)

    assert re.search(VOLUME_REPORT, REPORTED_VOLUME)
    assert match is not None
    assert match.groups() == ("7", "0badc0de")
    for malformed in MALFORMED_REPORTS:
        assert not re.search(VOLUME_REPORT, malformed)
        assert disks.VOLUME_REPORT.match(malformed) is None
