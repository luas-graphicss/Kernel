import gzip
import re
from pathlib import Path

import pytest

from kernel_tool.corpus.manifest import (
    IMAGE_DIRECTORY,
    IMAGE_SUFFIX,
    MANIFEST,
    MAX_IMAGE_BYTES,
    CorpusImage,
    check_corpus,
    differences,
    image_file,
    load_corpus,
    read_image,
    write_images,
)
from kernel_tool.corpus.recipes import RECIPES, build
from kernel_tool.outcome import CheckError
from kernel_tool.storage.volumes import Verdict, verify_image

REPOSITORY = Path(__file__).resolve().parents[2]
CORPUS = REPOSITORY / "tests" / "faults" / "storage"
TRUNCATED_PREFIX = "truncated-"
REQUIRED_TRUNCATIONS = 3
ENTRY = '[[image]]\nname = "{name}"\nverdict = "{verdict}"\nreason = "clean"\n'
VALID_ENTRY = ENTRY.format(name="valid", verdict="mountable")


def corpus_image(name: str, file: Path, verdict: Verdict) -> CorpusImage:
    return CorpusImage(name, file, verdict, "clean", None, None, None)


def test_every_image_of_the_corpus_matches_its_manifest() -> None:
    reports, failures = check_corpus(CORPUS)

    assert failures == []
    assert len(reports) == len(load_corpus(CORPUS))


def test_the_manifest_lists_exactly_the_images_that_have_a_recipe() -> None:
    listed = {image.name for image in load_corpus(CORPUS)}
    stored = {path.name.removesuffix(IMAGE_SUFFIX) for path in (CORPUS / IMAGE_DIRECTORY).iterdir()}

    assert listed == set(RECIPES)
    assert stored == set(RECIPES)


@pytest.mark.parametrize("name", sorted(RECIPES))
def test_a_stored_image_is_what_its_recipe_builds(name: str) -> None:
    assert gzip.decompress(image_file(CORPUS, name).read_bytes()) == build(name)


def test_the_corpus_holds_valid_truncated_incompatible_and_corrupted_volumes() -> None:
    images = load_corpus(CORPUS)
    truncated = [image for image in images if image.name.startswith(TRUNCATED_PREFIX)]

    assert {image.verdict for image in images} == set(Verdict)
    assert len(truncated) >= REQUIRED_TRUNCATIONS
    assert all(image.verdict is Verdict.CORRUPTED for image in truncated)


def test_images_are_written_the_same_way_every_time(tmp_path: Path) -> None:
    first = {path.name: path.read_bytes() for path in write_images(tmp_path)}
    second = {path.name: path.read_bytes() for path in write_images(tmp_path)}

    assert first == second
    assert set(first) == {f"{name}{IMAGE_SUFFIX}" for name in RECIPES}


def test_an_unknown_recipe_is_refused() -> None:
    with pytest.raises(CheckError, match="no recipe named 'missing'"):
        build("missing")


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("", "non-empty list"),
        ('title = "corpus"\n' + VALID_ENTRY, "non-empty list"),
        ('[[image]]\nname = "valid"\n', "needs a name, a verdict and a reason"),
        (VALID_ENTRY + 'colour = "red"\n', "unknown keys: colour"),
        (ENTRY.format(name="Not Valid", verdict="mountable"), "is not a valid image name"),
        (ENTRY.format(name="valid", verdict="pristine"), "the verdict or the reason is not valid"),
        (VALID_ENTRY + "generation = true\n", "generation must be an integer"),
        (VALID_ENTRY + "digest = 5\n", "digest and problem must be strings"),
        (VALID_ENTRY * 2, "an image name is repeated"),
        ("[[image", "manifest.toml"),
    ],
)
def test_a_malformed_manifest_is_refused(tmp_path: Path, text: str, problem: str) -> None:
    (tmp_path / MANIFEST).write_text(text, encoding="utf-8")

    with pytest.raises(CheckError, match=problem):
        load_corpus(tmp_path)


def test_a_corpus_without_a_manifest_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CheckError, match=re.escape(MANIFEST)):
        load_corpus(tmp_path)


def test_differences_name_each_field_that_disagrees_with_the_manifest() -> None:
    report = verify_image(build("populated-volume"))
    expected = CorpusImage(
        "populated-volume",
        Path("unused"),
        Verdict.MOUNTABLE,
        "clean",
        report.generation,
        report.digest,
        None,
    )
    wrong = CorpusImage(
        "populated-volume",
        Path("unused"),
        Verdict.READ_ONLY,
        "recovered",
        9,
        "00000000",
        "superblock checksum does not match",
    )

    assert differences(expected, report) == []
    assert len(differences(wrong, report)) == 5
    assert all(line.startswith("populated-volume: ") for line in differences(wrong, report))


def test_an_image_that_cannot_be_expanded_within_the_limit_is_refused(tmp_path: Path) -> None:
    huge = corpus_image("huge", tmp_path / "huge.img.gz", Verdict.CORRUPTED)
    broken = corpus_image("broken", tmp_path / "broken.img.gz", Verdict.CORRUPTED)
    missing = corpus_image("missing", tmp_path / "missing.img.gz", Verdict.CORRUPTED)
    huge.file.write_bytes(gzip.compress(bytes(MAX_IMAGE_BYTES + 1)))
    broken.file.write_bytes(b"not a gzip stream")

    with pytest.raises(CheckError, match="expands beyond"):
        read_image(huge)
    with pytest.raises(CheckError, match=re.escape(broken.file.name)):
        read_image(broken)
    with pytest.raises(CheckError, match=re.escape(missing.file.name)):
        read_image(missing)
