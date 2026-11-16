from pathlib import Path

import pytest
from kernel_tool.outcome import CheckError
from kernel_tool.toolchain.lock import load_lock

VALID_SHA256 = "a" * 64

VALID_LOCK = f"""
version = 1
host = "linux-x86_64"
source_date_epoch = 1787581954

[[artifact]]
name = "compiler"
version = "1.0"
url = "https://example.org/releases/compiler-1.0.tar.gz"
sha256 = "{VALID_SHA256}"
size = 10
root = "compiler-1.0"
license = "MIT"
include = ["bin"]

[[component]]
name = "firmware"
version = "2.0"
artifact = "compiler"
path = "share/firmware.bin"
sha256 = "{VALID_SHA256}"
license = "BSD-2-Clause"
"""


def write_lock(tmp_path: Path, content: str) -> Path:
    lock_file = tmp_path / "toolchain.lock.toml"
    lock_file.write_text(content, encoding="utf-8")
    return lock_file


def test_load_lock_reads_artifacts_and_components(tmp_path: Path) -> None:
    lock = load_lock(write_lock(tmp_path, VALID_LOCK))

    artifact = lock.artifact("compiler")
    assert artifact.archive_name == "compiler-1.0.tar.gz"
    assert artifact.include == ("bin",)
    assert lock.component("firmware").artifact == "compiler"
    assert lock.source_date_epoch == 1787581954


def test_repository_lock_is_valid() -> None:
    repository_lock = Path(__file__).resolve().parents[2] / "toolchain.lock.toml"

    lock = load_lock(repository_lock)

    assert {artifact.name for artifact in lock.artifacts} == {
        "riscv-none-elf-gcc",
        "qemu-riscv",
        "micropython",
    }
    assert lock.component("opensbi").artifact == "qemu-riscv"


@pytest.mark.parametrize(
    ("original", "replacement", "message"),
    [
        ("version = 1\n", "version = 2\n", "unsupported lock version"),
        ("https://example.org", "http://example.org", "url must use https"),
        (f'sha256 = "{VALID_SHA256}"\nsize', 'sha256 = "ABC"\nsize', "sha256 must be"),
        ('root = "compiler-1.0"', 'root = "../outside"', "must stay inside the artifact"),
        ('artifact = "compiler"', 'artifact = "missing"', "unknown artifact"),
        ("size = 10", "size = -1", "non-negative integer"),
    ],
)
def test_load_lock_rejects_invalid_entries(
    tmp_path: Path, original: str, replacement: str, message: str
) -> None:
    assert original in VALID_LOCK
    lock_file = write_lock(tmp_path, VALID_LOCK.replace(original, replacement))

    with pytest.raises(CheckError, match=message):
        load_lock(lock_file)


def test_unknown_artifact_lookup_fails(tmp_path: Path) -> None:
    lock = load_lock(write_lock(tmp_path, VALID_LOCK))

    with pytest.raises(CheckError, match="no artifact named 'emulator'"):
        lock.artifact("emulator")
