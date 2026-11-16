import gzip
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.corpus.recipes import RECIPES
from kernel_tool.outcome import CheckError
from kernel_tool.storage.volumes import Verdict, VolumeReport, verify_image

MANIFEST = "manifest.toml"
IMAGE_DIRECTORY = "images"
IMAGE_SUFFIX = ".img.gz"
MAX_IMAGE_BYTES = 1 << 24
NAME_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
REQUIRED_KEYS = {"name", "verdict", "reason"}
OPTIONAL_KEYS = {"generation", "digest", "problem"}
UNCOMPRESSED_TIME = 0
COMPRESSION_LEVEL = 9


@dataclass(frozen=True, slots=True)
class CorpusImage:
    name: str
    file: Path
    verdict: Verdict
    reason: str
    generation: int | None
    digest: str | None
    problem: str | None


def image_file(directory: Path, name: str) -> Path:
    return directory / IMAGE_DIRECTORY / f"{name}{IMAGE_SUFFIX}"


def load_corpus(directory: Path) -> tuple[CorpusImage, ...]:
    manifest = directory / MANIFEST
    try:
        with manifest.open("rb") as source:
            document = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CheckError(f"{manifest}: {error}") from error
    listed = document.get("image")
    if not isinstance(listed, list) or not listed or set(document) != {"image"}:
        raise CheckError(f"{manifest}: the corpus is a non-empty list of [[image]] tables")
    images = tuple(_corpus_image(directory, manifest, entry) for entry in listed)
    names = [image.name for image in images]
    if len(set(names)) != len(names):
        raise CheckError(f"{manifest}: an image name is repeated")
    return images


def read_image(image: CorpusImage) -> bytes:
    try:
        with gzip.open(image.file, "rb") as source:
            content = source.read(MAX_IMAGE_BYTES + 1)
    except (OSError, EOFError) as error:
        raise CheckError(f"{image.file}: {error}") from error
    if len(content) > MAX_IMAGE_BYTES:
        raise CheckError(f"{image.file}: expands beyond {MAX_IMAGE_BYTES} bytes")
    return content


def differences(image: CorpusImage, report: VolumeReport) -> list[str]:
    problems = [slot.problem for slot in report.slots]
    compared = (
        ("verdict", image.verdict.value, report.verdict.value),
        ("reason", image.reason, report.reason),
        ("generation", image.generation, report.generation),
        ("digest", image.digest, report.digest),
    )
    found = [
        f"{image.name}: {field} is {actual!r}, the manifest expects {expected!r}"
        for field, expected, actual in compared
        if expected != actual
    ]
    if image.problem is not None and image.problem not in problems:
        found.append(
            f"{image.name}: no superblock reports {image.problem!r}; they report {problems!r}"
        )
    return found


def check_corpus(directory: Path) -> tuple[list[VolumeReport], list[str]]:
    reports = []
    failures = []
    for image in load_corpus(directory):
        report = verify_image(read_image(image))
        reports.append(report)
        failures.extend(differences(image, report))
    return reports, failures


def write_images(directory: Path) -> list[Path]:
    written = []
    (directory / IMAGE_DIRECTORY).mkdir(parents=True, exist_ok=True)
    for name, recipe in RECIPES.items():
        path = image_file(directory, name)
        path.write_bytes(gzip.compress(recipe(), COMPRESSION_LEVEL, mtime=UNCOMPRESSED_TIME))
        written.append(path)
    return written


def _corpus_image(directory: Path, manifest: Path, entry: object) -> CorpusImage:
    if not isinstance(entry, dict) or REQUIRED_KEYS - set(entry):
        raise CheckError(f"{manifest}: each [[image]] needs a name, a verdict and a reason")
    unknown = sorted(set(entry) - REQUIRED_KEYS - OPTIONAL_KEYS)
    if unknown:
        raise CheckError(f"{manifest}: unknown keys: {', '.join(unknown)}")
    name, verdict, reason = entry["name"], entry["verdict"], entry["reason"]
    generation = entry.get("generation")
    digest = entry.get("digest")
    problem = entry.get("problem")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise CheckError(f"{manifest}: {name!r} is not a valid image name")
    if not isinstance(reason, str) or verdict not in tuple(Verdict):
        raise CheckError(f"{manifest}: {name}: the verdict or the reason is not valid")
    if generation is not None and (isinstance(generation, bool) or not isinstance(generation, int)):
        raise CheckError(f"{manifest}: {name}: generation must be an integer")
    if not all(value is None or isinstance(value, str) for value in (digest, problem)):
        raise CheckError(f"{manifest}: {name}: digest and problem must be strings")
    return CorpusImage(
        name=name,
        file=image_file(directory, name),
        verdict=Verdict(verdict),
        reason=reason,
        generation=generation,
        digest=digest,
        problem=problem,
    )
