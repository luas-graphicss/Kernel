import json
from pathlib import Path

import pytest

from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    FORMAT_VERSION,
    SUPERBLOCK_SLOTS,
    SUPERBLOCK_VERSION,
)
from kernel_tool.outcome import CheckError
from kernel_tool.release.checksums import write_checksums
from kernel_tool.release.installation import (
    install,
    open_installation,
    rollback,
    update,
    volume_format,
)
from kernel_tool.storage.volumes import Verdict, verify_image

NEWER_FORMAT = FORMAT_VERSION + 1


def bundle(directory: Path, version: str, formats: list[int]) -> Path:
    release = directory / "bundles" / f"kernel-{version}-test"
    release.mkdir(parents=True)
    manifest = {"version": version, "profile": "test", "volume_formats": formats}
    (release / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (release / "kernel.elf").write_bytes(version.encode("ascii"))
    write_checksums(release)
    return release


def mark_format(image: Path, version: int) -> None:
    content = bytearray(image.read_bytes())
    for slot in range(SUPERBLOCK_SLOTS):
        offset = slot * BLOCK_BYTES + SUPERBLOCK_VERSION
        content[offset : offset + 4] = version.to_bytes(4, "little")
    image.write_bytes(content)


def test_the_first_installation_creates_a_volume_the_guest_can_mount(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()

    installed = install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), target)

    assert installed.current == "kernel-1.0.0-test"
    assert installed.previous is None
    assert (installed.release / "kernel.elf").read_bytes() == b"1.0.0"
    assert verify_image(installed.data_image.read_bytes()).verdict is Verdict.MOUNTABLE
    assert volume_format(installed.data_image) == FORMAT_VERSION
    assert open_installation(target) == installed


def test_an_installation_is_not_made_over_another(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), target)

    with pytest.raises(CheckError, match="already holds an installation"):
        install(bundle(tmp_path, "1.0.1", [FORMAT_VERSION]), target)


def test_an_update_keeps_the_volume_and_the_earlier_release(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    first = install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), target)
    volume = first.data_image.read_bytes()

    updated = update(bundle(tmp_path, "1.0.1", [FORMAT_VERSION]), target)

    assert (updated.current, updated.previous) == ("kernel-1.0.1-test", "kernel-1.0.0-test")
    assert updated.data_image.read_bytes() == volume
    assert (first.release / "kernel.elf").is_file()


def test_a_rollback_returns_to_the_earlier_release_with_the_same_volume(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), target)
    updated = update(bundle(tmp_path, "1.0.1", [FORMAT_VERSION]), target)
    volume = updated.data_image.read_bytes()

    returned = rollback(target)

    assert (returned.current, returned.previous) == ("kernel-1.0.0-test", "kernel-1.0.1-test")
    assert returned.data_image.read_bytes() == volume


def test_a_rollback_is_refused_when_the_earlier_release_cannot_read_the_volume(
    tmp_path: Path,
) -> None:
    target = tmp_path / "site"
    target.mkdir()
    install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), target)
    updated = update(bundle(tmp_path, "2.0.0", [FORMAT_VERSION, NEWER_FORMAT]), target)
    mark_format(updated.data_image, NEWER_FORMAT)
    volume = updated.data_image.read_bytes()

    with pytest.raises(CheckError, match=f"volume format {NEWER_FORMAT}"):
        rollback(target)

    assert open_installation(target).current == "kernel-2.0.0-test"
    assert updated.data_image.read_bytes() == volume


def test_an_update_that_cannot_read_the_volume_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    installed = install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), target)
    mark_format(installed.data_image, NEWER_FORMAT)

    with pytest.raises(CheckError, match="left untouched"):
        update(bundle(tmp_path, "1.0.1", [FORMAT_VERSION]), target)

    assert open_installation(target).current == "kernel-1.0.0-test"


def test_an_existing_volume_is_kept_by_a_first_installation(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    earlier = install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), tmp_path / "earlier")
    (target / "data.img").write_bytes(earlier.data_image.read_bytes() + b"")
    kept = (target / "data.img").read_bytes()

    installed = install(bundle(tmp_path, "1.0.1", [FORMAT_VERSION]), target)

    assert installed.data_image.read_bytes() == kept


def test_an_unrecognizable_volume_stops_the_installation(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    (target / "data.img").write_bytes(b"not a volume" * 1000)

    with pytest.raises(CheckError, match="no recognizable volume"):
        install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), target)

    assert (target / "data.img").read_bytes() == b"not a volume" * 1000
    assert not (target / "installation.json").exists()


def test_a_bundle_that_was_changed_is_not_installed(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    release = bundle(tmp_path, "1.0.0", [FORMAT_VERSION])
    (release / "kernel.elf").write_bytes(b"tampered")

    with pytest.raises(CheckError, match="does not match its checksum"):
        install(release, target)

    assert not (target / "installation.json").exists()


def test_a_rollback_needs_an_earlier_release(tmp_path: Path) -> None:
    target = tmp_path / "site"
    target.mkdir()
    install(bundle(tmp_path, "1.0.0", [FORMAT_VERSION]), target)

    with pytest.raises(CheckError, match="no earlier release"):
        rollback(target)
