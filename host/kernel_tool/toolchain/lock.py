import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.outcome import CheckError

SUPPORTED_LOCK_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class Artifact:
    name: str
    version: str
    url: str
    sha256: str
    size: int
    root: str
    license: str
    include: tuple[str, ...]

    @property
    def archive_name(self) -> str:
        return self.url.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class Component:
    name: str
    version: str
    artifact: str
    path: str
    sha256: str
    license: str


@dataclass(frozen=True, slots=True)
class ToolchainLock:
    host: str
    source_date_epoch: int
    artifacts: tuple[Artifact, ...]
    components: tuple[Component, ...]

    def artifact(self, name: str) -> Artifact:
        for artifact in self.artifacts:
            if artifact.name == name:
                return artifact
        raise CheckError(f"toolchain lock has no artifact named {name!r}")

    def component(self, name: str) -> Component:
        for component in self.components:
            if component.name == name:
                return component
        raise CheckError(f"toolchain lock has no component named {name!r}")


def load_lock(path: Path) -> ToolchainLock:
    try:
        with path.open("rb") as source:
            document = tomllib.load(source)
    except tomllib.TOMLDecodeError as error:
        raise CheckError(f"{path}: {error}") from error

    version = document.get("version")
    if version != SUPPORTED_LOCK_VERSION:
        raise CheckError(f"{path}: unsupported lock version {version!r}")

    artifacts = tuple(_parse_artifact(entry) for entry in _tables(document, "artifact"))
    components = tuple(_parse_component(entry) for entry in _tables(document, "component"))
    known_artifacts = {artifact.name for artifact in artifacts}
    for component in components:
        if component.artifact not in known_artifacts:
            raise CheckError(
                f"component {component.name!r} refers to unknown artifact {component.artifact!r}"
            )

    return ToolchainLock(
        host=_text(document, "host", "lock"),
        source_date_epoch=_integer(document, "source_date_epoch", "lock"),
        artifacts=artifacts,
        components=components,
    )


def _parse_artifact(entry: dict[str, object]) -> Artifact:
    name = _text(entry, "name", "artifact")
    context = f"artifact {name!r}"
    url = _text(entry, "url", context)
    if not url.startswith("https://"):
        raise CheckError(f"{context}: url must use https")
    include = entry.get("include", [])
    if not isinstance(include, list) or not all(isinstance(item, str) for item in include):
        raise CheckError(f"{context}: include must be a list of paths")
    return Artifact(
        name=name,
        version=_text(entry, "version", context),
        url=url,
        sha256=_digest(entry, context),
        size=_integer(entry, "size", context),
        root=_relative_path(entry, "root", context),
        license=_text(entry, "license", context),
        include=tuple(include),
    )


def _parse_component(entry: dict[str, object]) -> Component:
    name = _text(entry, "name", "component")
    context = f"component {name!r}"
    return Component(
        name=name,
        version=_text(entry, "version", context),
        artifact=_text(entry, "artifact", context),
        path=_relative_path(entry, "path", context),
        sha256=_digest(entry, context),
        license=_text(entry, "license", context),
    )


def _tables(document: dict[str, object], key: str) -> list[dict[str, object]]:
    tables = document.get(key, [])
    if not isinstance(tables, list) or not all(isinstance(table, dict) for table in tables):
        raise CheckError(f"lock: {key} must be an array of tables")
    return tables


def _text(table: dict[str, object], key: str, context: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise CheckError(f"{context}: {key} must be a non-empty string")
    return value


def _integer(table: dict[str, object], key: str, context: str) -> int:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CheckError(f"{context}: {key} must be a non-negative integer")
    return value


def _digest(table: dict[str, object], context: str) -> str:
    value = _text(table, "sha256", context)
    if not SHA256_PATTERN.fullmatch(value):
        raise CheckError(f"{context}: sha256 must be 64 lowercase hexadecimal digits")
    return value


def _relative_path(table: dict[str, object], key: str, context: str) -> str:
    value = _text(table, key, context)
    parts = Path(value).parts
    if Path(value).is_absolute() or ".." in parts:
        raise CheckError(f"{context}: {key} must stay inside the artifact")
    return value
