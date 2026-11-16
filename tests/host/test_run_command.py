from pathlib import Path

import pytest

from kernel_tool.commands.emulation import asks_restart, system_drives
from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.qemu.drives import FileDrive
from kernel_tool.qemu.session import SessionResult
from kernel_tool.storage.volumes import Verdict, verify_image

SHUTDOWN = "boot: hart=0\nsystem: shutdown=complete clean=1\nkernel: status=ok\n"
RESTART = (
    "boot: hart=0\nsystem: shutdown=complete clean=1\nkernel: power=restart\nkernel: status=ok\n"
)


def session(transcript: str, exit_code: int | None = 0) -> SessionResult:
    return SessionResult(
        exit_code=exit_code, transcript=transcript, emulator_messages="", duration_seconds=1.0
    )


def test_a_system_that_shut_down_is_not_booted_again() -> None:
    assert asks_restart(session(SHUTDOWN), None) is False


def test_a_system_that_asked_for_a_restart_is_booted_again() -> None:
    assert asks_restart(session(RESTART), None) is True


def test_a_failed_or_silent_kernel_ends_the_run_with_a_failure() -> None:
    with pytest.raises(CheckError, match="status failed"):
        asks_restart(session(SHUTDOWN.replace("status=ok", "status=failed")), None)
    with pytest.raises(CheckError, match="status missing"):
        asks_restart(session("boot: hart=0\n"), None)


def test_a_boot_past_its_deadline_and_a_failed_emulator_are_told_apart() -> None:
    with pytest.raises(CheckError, match="did not stop within 30 seconds"):
        asks_restart(session(SHUTDOWN, None), 30.0)
    with pytest.raises(InfrastructureError, match="exited with status 1"):
        asks_restart(session(SHUTDOWN, 1), None)


def test_the_data_volume_is_created_once_and_kept_between_runs(tmp_path: Path) -> None:
    boot_image = tmp_path / "boot.img"

    boot, data = system_drives(boot_image, tmp_path)

    assert boot == FileDrive("kernel-boot", boot_image, read_only=True)
    assert isinstance(data, FileDrive)
    assert data == FileDrive("kernel-data", tmp_path / "data.img")
    assert verify_image(data.image.read_bytes()).verdict is Verdict.MOUNTABLE
    data.image.write_bytes(b"kept")
    system_drives(boot_image, tmp_path)
    assert data.image.read_bytes() == b"kept"
