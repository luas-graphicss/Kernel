from pathlib import Path

import pytest

from kernel_tool.outcome import CheckError
from kernel_tool.profiles.loader import DEFAULT_PROFILE, load_profile

REPOSITORY = Path(__file__).resolve().parents[2]


def copy_profile(tmp_path: Path, original: str, replacement: str) -> Path:
    source = (REPOSITORY / "config" / "profiles" / f"{DEFAULT_PROFILE}.toml").read_text("utf-8")
    assert original in source
    directory = tmp_path / "config" / "profiles"
    directory.mkdir(parents=True)
    (directory / f"{DEFAULT_PROFILE}.toml").write_text(
        source.replace(original, replacement), encoding="utf-8"
    )
    return tmp_path


def test_reference_profile_matches_the_platform_contract() -> None:
    profile = load_profile(REPOSITORY, DEFAULT_PROFILE)

    assert profile.machine.memory_mib == 256
    assert profile.machine.harts == 1
    assert profile.machine.firmware == "opensbi"
    assert profile.layout.kernel_base == 0x80200000
    assert profile.limits.processes == 16
    assert profile.limits.supervisor_heap_bytes == 8 * 1024 * 1024
    assert profile.limits.process_heap_bytes == 4 * 1024 * 1024
    assert profile.limits.capabilities_per_process == 128


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        ("harts = 1", "harts = 0", "harts must be a positive integer"),
        ("harts = 1", 'harts = "one"', "harts must be a positive integer"),
        ('cpu = "rv64,h=off,v=off"\n', "", r"\[machine\] is missing cpu"),
        ("processes = 16", "processes = 16\nthreads = 4", "unknown keys: threads"),
        ("memory_mib = 256", "memory_mib = 128", "bytes of memory"),
        ("user_heap_bytes = 0x100000", "user_heap_bytes = 0x800000", "heap limit of a process"),
        (
            "[deadlines]\nboot_seconds = 60\nselftest_seconds = 600\nsoak_seconds = 900\n",
            "",
            r"missing the \[deadlines\] table",
        ),
        ("selftest_seconds = 600\n", "", r"\[deadlines\] is missing selftest_seconds"),
        ("soak_seconds = 900\n", "", r"\[deadlines\] is missing soak_seconds"),
        ('name = "qemu-riscv64"', 'name = "other"', "name must be"),
    ],
)
def test_invalid_profiles_are_rejected(
    tmp_path: Path, original: str, replacement: str, message: str
) -> None:
    root = copy_profile(tmp_path, original, replacement)

    with pytest.raises(CheckError, match=message):
        load_profile(root, DEFAULT_PROFILE)


@pytest.mark.parametrize("name", ["../secrets", "Profile", "qemu riscv64", ""])
def test_profile_names_cannot_leave_the_profile_directory(name: str) -> None:
    with pytest.raises(CheckError, match="invalid profile name"):
        load_profile(REPOSITORY, name)


def test_unknown_profile_is_reported() -> None:
    with pytest.raises(CheckError, match="does not exist"):
        load_profile(REPOSITORY, "qemu-riscv32")
