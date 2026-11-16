import hashlib
import logging
import shutil
import tarfile
import urllib.request
from collections.abc import Iterator
from pathlib import Path

from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.toolchain.lock import Artifact

DOWNLOAD_TIMEOUT_SECONDS = 60
CHUNK_BYTES = 1 << 20
COMPLETE_MARKER = ".kernel-tool-complete"

logger = logging.getLogger(__name__)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_artifact(artifact: Artifact, cache_dir: Path) -> Path:
    destination = cache_dir / "tools" / artifact.root
    marker = destination / COMPLETE_MARKER
    if marker.is_file() and marker.read_text(encoding="ascii").strip() == artifact.sha256:
        return destination

    archive = _ensure_archive(artifact, cache_dir / "archives")
    logger.info("unpacking %s %s", artifact.name, artifact.version)
    _extract(artifact, archive, destination)
    marker.write_text(f"{artifact.sha256}\n", encoding="ascii")
    return destination


def _ensure_archive(artifact: Artifact, archives_dir: Path) -> Path:
    archive = archives_dir / artifact.archive_name
    if archive.is_file():
        if sha256_file(archive) == artifact.sha256:
            return archive
        archive.unlink()

    archives_dir.mkdir(parents=True, exist_ok=True)
    logger.info("downloading %s %s", artifact.name, artifact.version)
    _download(artifact, archive)
    return archive


def _download(artifact: Artifact, archive: Path) -> None:
    partial = archive.with_name(f"{archive.name}.part")
    digest = hashlib.sha256()
    try:
        with (
            urllib.request.urlopen(artifact.url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response,
            partial.open("wb") as output,
        ):
            while chunk := response.read(CHUNK_BYTES):
                digest.update(chunk)
                output.write(chunk)
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise InfrastructureError(f"download of {artifact.url} failed: {error}") from error

    if digest.hexdigest() != artifact.sha256:
        partial.unlink()
        raise CheckError(
            f"{artifact.archive_name}: sha256 {digest.hexdigest()} "
            f"does not match the lock ({artifact.sha256})"
        )
    partial.replace(archive)


def _extract(artifact: Artifact, archive: Path, destination: Path) -> None:
    staging = destination.with_name(f"{destination.name}.staging")
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(destination, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with tarfile.open(archive) as bundle:
            bundle.extractall(staging, members=_selected_members(bundle, artifact), filter="data")
    except tarfile.TarError as error:
        shutil.rmtree(staging)
        raise CheckError(f"{artifact.archive_name}: unsafe or corrupt archive: {error}") from error

    extracted_root = staging / artifact.root
    if not extracted_root.is_dir():
        shutil.rmtree(staging)
        raise CheckError(f"{artifact.archive_name}: missing top-level directory {artifact.root}")
    extracted_root.replace(destination)
    shutil.rmtree(staging)


def _selected_members(bundle: tarfile.TarFile, artifact: Artifact) -> Iterator[tarfile.TarInfo]:
    selected = tuple(f"{artifact.root}/{entry}" for entry in artifact.include)
    for member in bundle:
        if not selected or any(
            member.name == entry or member.name.startswith(f"{entry}/") for entry in selected
        ):
            yield member
