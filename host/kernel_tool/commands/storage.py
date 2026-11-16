import argparse
import json
import logging
import sys
from pathlib import Path

from kernel_tool.commands.options import CommandRegistry
from kernel_tool.corpus.manifest import MANIFEST, check_corpus, write_images
from kernel_tool.outcome import CheckError, ExitCode
from kernel_tool.storage.volumes import (
    TreeEntry,
    Verdict,
    VolumeReport,
    create_image,
    list_tree,
    verify_image,
)
from kernel_tool.workspace import Workspace

DEFAULT_BLOCKS = 256
DEFAULT_VOLUME = 0x6B65726E656C
MAX_IMAGE_BYTES = 1 << 30
READABLE = (Verdict.MOUNTABLE, Verdict.READ_ONLY)
HEXADECIMAL = 16

logger = logging.getLogger(__name__)


def register(commands: CommandRegistry) -> None:
    create = commands.add_parser(
        "create-volume", help="write a new empty volume to an image file that does not exist"
    )
    create.add_argument("image", type=Path, help="image file to create")
    create.add_argument(
        "--blocks",
        type=int,
        default=DEFAULT_BLOCKS,
        help=f"size in blocks of 4096 bytes (default: {DEFAULT_BLOCKS})",
    )
    create.add_argument(
        "--volume",
        default=f"{DEFAULT_VOLUME:x}",
        help="volume identifier in hexadecimal",
    )
    create.set_defaults(handler=run_create)

    verify = commands.add_parser(
        "verify-filesystem",
        help="check a volume image, or every image of a corpus against its manifest",
    )
    target = verify.add_mutually_exclusive_group(required=True)
    target.add_argument("--image", type=Path, help="volume image to check")
    target.add_argument("--corpus", type=Path, help=f"directory with a {MANIFEST}")
    verify.set_defaults(handler=run_verify)

    inspect = commands.add_parser(
        "inspect-volume", help="print the superblocks and the tree of a volume image"
    )
    inspect.add_argument("image", type=Path, help="volume image to read")
    inspect.add_argument("--json", action="store_true", help="print the metadata as JSON")
    inspect.set_defaults(handler=run_inspect)

    corpus = commands.add_parser(
        "build-corpus", help="write the images of the storage corpus from their recipes"
    )
    corpus.add_argument("corpus", type=Path, help=f"directory with a {MANIFEST}")
    corpus.set_defaults(handler=run_build_corpus)


def run_create(_workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    image: Path = options.image
    try:
        volume = int(options.volume, HEXADECIMAL)
    except ValueError as error:
        raise CheckError(f"the volume identifier is not hexadecimal: {options.volume}") from error
    content = create_image(options.blocks, volume)
    try:
        with image.open("xb") as output:
            output.write(content)
    except FileExistsError as error:
        raise CheckError(f"{image} exists; a volume is created only in a new file") from error
    logger.info("created %s with %d blocks", image, options.blocks)
    return ExitCode.OK


def run_verify(_workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    corpus: Path | None = options.corpus
    if corpus is not None:
        return verify_corpus(corpus)
    report = verify_image(read_image(options.image))
    sys.stdout.write(format_report(report))
    if report.verdict not in READABLE:
        raise CheckError(f"{options.image} is {report.verdict.value}: {report.reason}")
    return ExitCode.OK


def verify_corpus(directory: Path) -> ExitCode:
    reports, failures = check_corpus(directory)
    for report in reports:
        sys.stdout.write(format_report(report))
    if failures:
        raise CheckError("the corpus does not match its manifest:\n" + "\n".join(failures))
    logger.info("%d corpus images match %s", len(reports), directory / MANIFEST)
    return ExitCode.OK


def run_inspect(_workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    content = read_image(options.image)
    report = verify_image(content)
    tree = list_tree(content) if report.verdict in READABLE else ()
    as_json: bool = options.json
    if as_json:
        document = report.to_document() | {
            "tree": [{"path": entry.path, "kind": entry.kind, "size": entry.size} for entry in tree]
        }
        sys.stdout.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(format_report(report) + format_tree(tree))
    return ExitCode.OK


def run_build_corpus(_workspace: Workspace, options: argparse.Namespace) -> ExitCode:
    directory: Path = options.corpus
    if not (directory / MANIFEST).is_file():
        raise CheckError(f"{directory} has no {MANIFEST}; the corpus is written next to it")
    for image in write_images(directory):
        logger.info("wrote %s", image)
    return ExitCode.OK


def read_image(image: Path) -> bytes:
    try:
        if image.stat().st_size > MAX_IMAGE_BYTES:
            raise CheckError(f"{image} is larger than the largest volume")
        return image.read_bytes()
    except OSError as error:
        raise CheckError(f"cannot read {image}: {error}") from error


def format_report(report: VolumeReport) -> str:
    lines = [f"volume verdict={report.verdict.value} reason={report.reason}"]
    if report.generation is not None:
        lines[0] += (
            f" generation={report.generation} blocks={report.used_blocks}/{report.total_blocks}"
            f" directories={report.directories} files={report.files}"
            f" bytes={report.file_bytes} digest={report.digest}"
        )
    for slot in report.slots:
        state = f"generation={slot.generation}" if slot.valid else "invalid"
        problem = f" problem={slot.problem!r}" if slot.problem else ""
        lines.append(f"superblock slot={slot.number} {state}{problem}")
    return "\n".join(lines) + "\n"


def format_tree(tree: tuple[TreeEntry, ...]) -> str:
    return "".join(f"{entry.kind} {entry.path} bytes={entry.size}\n" for entry in tree)
