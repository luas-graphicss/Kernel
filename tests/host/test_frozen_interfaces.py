from pathlib import Path

import pytest

from kernel_tool.outcome import CheckError
from kernel_tool.release.interfaces import (
    LOCK_FILE,
    check_interfaces,
    freeze_interfaces,
    load_interfaces,
)

REPOSITORY = Path(__file__).resolve().parents[2]
FROZEN_VERSION = "1.0"
LOCK_TEXT = """version = 1

[[interface]]
name = "sample"
version = "1.0"
digest = ""
sources = [
    "protocol",
    "single.h",
]
"""


def frozen_copy(root: Path) -> Path:
    (root / "specs").mkdir()
    (root / "protocol").mkdir()
    (root / "protocol" / "numbers.py").write_text("FIRST = 1\n", encoding="utf-8")
    (root / "protocol" / "notes.txt").write_text("not part of the interface\n", encoding="utf-8")
    (root / "single.h").write_text("#define SECOND 2\n", encoding="utf-8")
    (root / LOCK_FILE).write_text(LOCK_TEXT, encoding="utf-8")
    freeze_interfaces(root)
    return root


def test_the_frozen_interfaces_of_the_repository_match_their_digests() -> None:
    interfaces = load_interfaces(REPOSITORY)

    assert check_interfaces(REPOSITORY) == []
    assert {interface.version for interface in interfaces} == {FROZEN_VERSION}
    assert {interface.name for interface in interfaces} == {
        "abi",
        "service-protocol",
        "image-manifest",
        "configuration",
        "persistent-format",
    }


def test_a_change_to_a_frozen_source_is_reported_until_it_is_frozen_again(tmp_path: Path) -> None:
    root = frozen_copy(tmp_path)
    (root / "protocol" / "notes.txt").write_text("edited\n", encoding="utf-8")
    assert check_interfaces(root) == []

    (root / "protocol" / "numbers.py").write_text("FIRST = 3\n", encoding="utf-8")
    changed = check_interfaces(root)
    freeze_interfaces(root)

    assert len(changed) == 1 and changed[0].startswith("sample 1.0: its sources changed")
    assert check_interfaces(root) == []


def test_a_frozen_source_that_disappears_is_an_error(tmp_path: Path) -> None:
    root = frozen_copy(tmp_path)
    (root / "single.h").unlink()

    with pytest.raises(CheckError, match=r"single\.h does not exist"):
        check_interfaces(root)
