import json
from pathlib import Path

import pytest

from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    KIND_DIRECTORY,
    KIND_FILE,
    MAX_BLOCKS,
    MIN_BLOCKS,
    SUPERBLOCK_SLOTS,
)
from kernel_services.filesystem.volume import Volume
from kernel_tool.cli import main
from kernel_tool.corpus import recipes
from kernel_tool.corpus.manifest import load_corpus
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.storage.image_store import ImageStore
from kernel_tool.storage.volumes import TreeEntry, Verdict, create_image, list_tree, verify_image

REPOSITORY = Path(__file__).resolve().parents[2]
CORPUS = REPOSITORY / "tests" / "faults" / "storage"
VOLUME = 0x564F4C554D45
BLOCKS = 32
CREATED_BLOCKS = 16
ENTRY_TEXT = b"entry"
README_TEXT = b"read me"


def populated_image() -> bytes:
    store = ImageStore(create_image(BLOCKS, VOLUME))
    volume = Volume(store)
    notes = volume.create(volume.root(), b"notes", KIND_DIRECTORY)
    volume.write(volume.create(notes, b"entry.txt", KIND_FILE), 0, ENTRY_TEXT)
    volume.write(volume.create(volume.root(), b"readme.txt", KIND_FILE), 0, README_TEXT)
    volume.sync()
    return bytes(store.content)


def stored(directory: Path, name: str, content: bytes) -> Path:
    image = directory / name
    image.write_bytes(content)
    return image


@pytest.fixture(autouse=True)
def inside_the_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPOSITORY)


def test_a_new_volume_is_mountable_and_empty() -> None:
    report = verify_image(create_image(BLOCKS, VOLUME))

    assert (report.verdict, report.reason, report.generation) == (Verdict.MOUNTABLE, "clean", 1)
    assert (report.total_blocks, report.files, report.file_bytes) == (BLOCKS, 0, 0)
    assert list_tree(create_image(BLOCKS, VOLUME)) == ()


def test_the_size_of_a_volume_is_bounded() -> None:
    for blocks in (-1, 0, MIN_BLOCKS - 1, MAX_BLOCKS + 1):
        with pytest.raises(CheckError, match="a volume holds between"):
            create_image(blocks, VOLUME)
    assert len(create_image(MIN_BLOCKS, VOLUME)) == MIN_BLOCKS * BLOCK_BYTES


def test_the_tree_is_listed_in_path_order_with_kinds_and_sizes() -> None:
    notes, entry, readme = list_tree(populated_image())

    assert (notes.path, notes.kind) == ("/notes", "directory")
    assert entry == TreeEntry("/notes/entry.txt", "file", len(ENTRY_TEXT))
    assert readme == TreeEntry("/readme.txt", "file", len(README_TEXT))


def test_a_report_counts_what_the_tree_holds() -> None:
    report = verify_image(populated_image())

    assert (report.files, report.file_bytes) == (2, len(ENTRY_TEXT) + len(README_TEXT))
    assert report.generation == 2
    assert report.digest is not None
    assert len(report.digest) == 8
    assert [slot.number for slot in report.slots] == list(range(SUPERBLOCK_SLOTS))
    assert report.to_document()["verdict"] == "mountable"


def test_the_digest_depends_on_the_tree_and_not_on_how_it_was_written() -> None:
    store = ImageStore(create_image(BLOCKS, VOLUME))
    volume = Volume(store)
    readme = volume.create(volume.root(), b"readme.txt", KIND_FILE)
    volume.write(readme, 0, b"draft")
    volume.sync()
    volume.truncate(readme, 0)
    volume.write(readme, 0, README_TEXT)
    notes = volume.create(volume.root(), b"notes", KIND_DIRECTORY)
    volume.write(volume.create(notes, b"entry.txt", KIND_FILE), 0, ENTRY_TEXT)
    volume.sync()
    rewritten = verify_image(bytes(store.content))
    direct = verify_image(populated_image())

    assert rewritten.generation != direct.generation
    assert rewritten.digest == direct.digest
    assert verify_image(create_image(BLOCKS, VOLUME)).digest != direct.digest


@pytest.mark.parametrize(
    ("recipe", "verdict"),
    [
        ("populated-volume", Verdict.MOUNTABLE),
        ("newest-root-damaged", Verdict.READ_ONLY),
        ("both-superblocks-damaged", Verdict.CORRUPTED),
        ("unknown-format-version", Verdict.UNSUPPORTED),
    ],
)
def test_every_verdict_has_an_image_that_reaches_it(recipe: str, verdict: Verdict) -> None:
    assert verify_image(recipes.build(recipe)).verdict is verdict


def test_a_refused_image_still_reports_both_superblock_slots() -> None:
    report = verify_image(recipes.build("both-superblocks-damaged"))
    empty = verify_image(b"")

    assert (report.generation, report.digest, report.files) == (None, None, None)
    assert [slot.valid for slot in report.slots] == [False] * SUPERBLOCK_SLOTS
    assert all(slot.problem for slot in report.slots)
    assert (empty.verdict, empty.slots) == (Verdict.CORRUPTED, ())


def test_create_volume_writes_a_new_file_and_never_replaces_one(tmp_path: Path) -> None:
    image = tmp_path / "volume.img"
    other = tmp_path / "other.img"

    assert main(["create-volume", str(image), "--blocks", str(CREATED_BLOCKS)]) == ExitCode.OK
    created = image.read_bytes()
    assert len(created) == CREATED_BLOCKS * BLOCK_BYTES
    assert verify_image(created).verdict is Verdict.MOUNTABLE

    assert main(["create-volume", str(image)]) == ExitCode.FAILED
    assert image.read_bytes() == created
    assert main(["create-volume", str(other), "--volume", "not-hexadecimal"]) == ExitCode.FAILED
    assert main(["create-volume", str(other), "--blocks", "1"]) == ExitCode.FAILED
    assert not other.exists()


def test_verify_filesystem_passes_only_what_can_be_read_as_a_volume(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = stored(tmp_path, "good.img", populated_image())
    protected = stored(tmp_path, "protected.img", recipes.build("newest-root-damaged"))
    damaged = stored(tmp_path, "damaged.img", recipes.build("both-superblocks-damaged"))

    assert main(["verify-filesystem", "--image", str(good)]) == ExitCode.OK
    assert capsys.readouterr().out.startswith("volume verdict=mountable reason=clean generation=2 ")
    assert main(["verify-filesystem", "--image", str(protected)]) == ExitCode.OK
    assert capsys.readouterr().out.startswith(
        "volume verdict=read-only reason=newest-root-damaged "
    )
    assert main(["verify-filesystem", "--image", str(damaged)]) == ExitCode.FAILED
    assert capsys.readouterr().out.startswith("volume verdict=corrupted ")
    assert main(["verify-filesystem", "--image", str(tmp_path / "missing.img")]) == ExitCode.FAILED


def test_verify_filesystem_checks_every_image_of_the_corpus(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["verify-filesystem", "--corpus", str(CORPUS)]) == ExitCode.OK
    assert capsys.readouterr().out.count("volume verdict=") == len(load_corpus(CORPUS))


def test_inspect_volume_prints_the_tree_as_text_or_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    image = stored(tmp_path, "volume.img", populated_image())

    assert main(["inspect-volume", str(image)]) == ExitCode.OK
    text = capsys.readouterr().out
    assert main(["inspect-volume", str(image), "--json"]) == ExitCode.OK
    document = json.loads(capsys.readouterr().out)

    assert text.startswith("volume verdict=mountable ")
    assert "superblock slot=0 " in text
    assert f"file /notes/entry.txt bytes={len(ENTRY_TEXT)}\n" in text
    assert document["verdict"] == "mountable"
    assert {"path": "/readme.txt", "kind": "file", "size": len(README_TEXT)} in document["tree"]


def test_inspect_volume_describes_a_refused_image_without_a_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    damaged = stored(tmp_path, "damaged.img", recipes.build("both-superblocks-damaged"))

    assert main(["inspect-volume", str(damaged), "--json"]) == ExitCode.OK
    document = json.loads(capsys.readouterr().out)

    assert document["verdict"] == "corrupted"
    assert document["tree"] == []


def test_build_corpus_writes_only_next_to_a_manifest(tmp_path: Path) -> None:
    assert main(["build-corpus", str(tmp_path)]) == ExitCode.FAILED
    assert list(tmp_path.iterdir()) == []
