import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    SUPERBLOCK_MAGIC,
    SUPERBLOCK_SLOTS,
    SUPERBLOCK_VERSION,
)
from kernel_tool.outcome import CheckError
from kernel_tool.release.bundle import DATA_IMAGE, MANIFEST_FILE
from kernel_tool.release.checksums import require_intact
from kernel_tool.scenarios.disks import DATA_BLOCKS, DATA_VOLUME
from kernel_tool.storage.volumes import create_image

STATE_FILE = "installation.json"
RELEASES_DIRECTORY = "releases"
VERSION_BYTES = 4
BYTE_ORDER: Final = "little"
ENCODING = "utf-8"


@dataclass(frozen=True, slots=True)
class Installation:
    target: Path
    current: str
    previous: str | None

    @property
    def release(self) -> Path:
        return self.target / RELEASES_DIRECTORY / self.current

    @property
    def data_image(self) -> Path:
        return self.target / DATA_IMAGE


def open_installation(target: Path) -> Installation:
    state = target / STATE_FILE
    try:
        document = json.loads(state.read_text(encoding=ENCODING))
        current, previous = document["current"], document["previous"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CheckError(f"{target} holds no installation: {error}") from error
    if not isinstance(current, str) or not (previous is None or isinstance(previous, str)):
        raise CheckError(f"{state}: the installation state is malformed")
    return Installation(target, current, previous)


def install(bundle: Path, target: Path) -> Installation:
    if (target / STATE_FILE).exists():
        raise CheckError(f"{target} already holds an installation; update it instead")
    name = _checked_name(bundle)
    data = target / DATA_IMAGE
    if data.is_file():
        _require_compatible(bundle, data)
    _copy_release(bundle, target, name)
    if not data.is_file():
        data.write_bytes(create_image(DATA_BLOCKS, DATA_VOLUME))
    return _record(Installation(target, name, None))


def update(bundle: Path, target: Path) -> Installation:
    installed = open_installation(target)
    name = _checked_name(bundle)
    if name == installed.current:
        raise CheckError(f"{name} is the installed release")
    _require_compatible(bundle, installed.data_image)
    _copy_release(bundle, target, name)
    return _record(Installation(target, name, installed.current))


def rollback(target: Path) -> Installation:
    installed = open_installation(target)
    if installed.previous is None:
        raise CheckError("there is no earlier release to return to")
    earlier = target / RELEASES_DIRECTORY / installed.previous
    require_intact(earlier)
    _require_compatible(earlier, installed.data_image)
    return _record(Installation(target, installed.previous, installed.current))


def read_manifest(release: Path) -> dict[str, object]:
    path = release / MANIFEST_FILE
    try:
        document = json.loads(path.read_text(encoding=ENCODING))
    except (OSError, ValueError) as error:
        raise CheckError(f"{path}: cannot read the release manifest: {error}") from error
    if not isinstance(document, dict):
        raise CheckError(f"{path}: the release manifest is malformed")
    return document


def volume_format(image: Path) -> int | None:
    content = image.read_bytes()
    recorded = set()
    for slot in range(SUPERBLOCK_SLOTS):
        block = content[slot * BLOCK_BYTES : (slot + 1) * BLOCK_BYTES]
        if block.startswith(SUPERBLOCK_MAGIC):
            version = block[SUPERBLOCK_VERSION : SUPERBLOCK_VERSION + VERSION_BYTES]
            recorded.add(int.from_bytes(version, BYTE_ORDER))
    return recorded.pop() if len(recorded) == 1 else None


def _require_compatible(release: Path, data: Path) -> None:
    understood = read_manifest(release).get("volume_formats")
    if not isinstance(understood, list):
        raise CheckError(f"{release}: the manifest does not state the volume formats it reads")
    recorded = volume_format(data)
    if recorded is None:
        raise CheckError(
            f"{data} holds no recognizable volume; keep a copy and decide what to do with it "
            "before installing over it"
        )
    if recorded not in understood:
        raise CheckError(
            f"{data} is in volume format {recorded}, which this release does not read "
            f"(it reads {understood}); the volume was left untouched"
        )


def _checked_name(bundle: Path) -> str:
    require_intact(bundle)
    manifest = read_manifest(bundle)
    name = f"kernel-{manifest.get('version')}-{manifest.get('profile')}"
    if bundle.name != name:
        raise CheckError(f"{bundle} is named differently from its manifest ({name})")
    return name


def _copy_release(bundle: Path, target: Path, name: str) -> None:
    destination = target / RELEASES_DIRECTORY / name
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle, destination)
    require_intact(destination)


def _record(installation: Installation) -> Installation:
    state = {"current": installation.current, "previous": installation.previous}
    path = installation.target / STATE_FILE
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding=ENCODING)
    return installation
