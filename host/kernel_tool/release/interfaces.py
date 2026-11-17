import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.outcome import CheckError

LOCK_FILE = Path("specs") / "frozen-interfaces.toml"
LOCK_VERSION = 1
DIRECTORY_SUFFIXES = (".py", ".pyi", ".h")
SEPARATOR = b"\0"
ENCODING = "utf-8"
INTERFACE_FIELDS = {"name", "version", "digest", "sources"}


@dataclass(frozen=True, slots=True)
class Interface:
    name: str
    version: str
    digest: str
    sources: tuple[str, ...]


def load_interfaces(root: Path) -> tuple[Interface, ...]:
    path = root / LOCK_FILE
    try:
        with path.open("rb") as source:
            document = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CheckError(f"{path}: {error}") from error
    if document.get("version") != LOCK_VERSION:
        raise CheckError(f"{path}: unsupported version {document.get('version')!r}")
    listed = document.get("interface", [])
    if not isinstance(listed, list) or not listed:
        raise CheckError(f"{path}: no [[interface]] table")
    return tuple(_interface(path, entry) for entry in listed)


def source_digest(root: Path, sources: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for source in sources:
        for file in _files(root, source):
            digest.update(file.relative_to(root).as_posix().encode(ENCODING))
            digest.update(SEPARATOR)
            digest.update(file.read_bytes())
            digest.update(SEPARATOR)
    return digest.hexdigest()


def check_interfaces(root: Path) -> list[str]:
    return [
        f"{interface.name} {interface.version}: its sources changed after the freeze; "
        f"follow specs/compatibility.md and freeze it again"
        for interface in load_interfaces(root)
        if source_digest(root, interface.sources) != interface.digest
    ]


def frozen_text(root: Path) -> str:
    parts = [f"version = {LOCK_VERSION}\n"]
    for interface in load_interfaces(root):
        sources = "".join(f'    "{source}",\n' for source in interface.sources)
        parts.append(
            "\n[[interface]]\n"
            f'name = "{interface.name}"\n'
            f'version = "{interface.version}"\n'
            f'digest = "{source_digest(root, interface.sources)}"\n'
            f"sources = [\n{sources}]\n"
        )
    return "".join(parts)


def freeze_interfaces(root: Path) -> None:
    (root / LOCK_FILE).write_text(frozen_text(root), encoding=ENCODING)


def _interface(path: Path, entry: object) -> Interface:
    if not isinstance(entry, dict) or set(entry) != INTERFACE_FIELDS:
        raise CheckError(f"{path}: each [[interface]] needs {sorted(INTERFACE_FIELDS)}")
    sources = entry["sources"]
    texts = (entry["name"], entry["version"], entry["digest"])
    if not all(isinstance(text, str) for text in texts) or not isinstance(sources, list):
        raise CheckError(f"{path}: an [[interface]] has a field of the wrong type")
    if not sources or not all(isinstance(source, str) for source in sources):
        raise CheckError(f"{path}: the interface {entry['name']} lists no source")
    return Interface(entry["name"], entry["version"], entry["digest"], tuple(sources))


def _files(root: Path, source: str) -> list[Path]:
    path = root / source
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise CheckError(f"the frozen source {source} does not exist")
    return sorted(
        file for file in path.rglob("*") if file.is_file() and file.suffix in DIRECTORY_SUFFIXES
    )
