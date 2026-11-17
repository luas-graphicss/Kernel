import tomllib
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.outcome import CheckError
from kernel_tool.toolchain.lock import ToolchainLock

REVIEW_FILE = Path("config") / "release" / "advisories.toml"
REVIEW_VERSION = 1
BLOCKING_SEVERITIES = ("high", "critical")


@dataclass(frozen=True, slots=True)
class Advisory:
    identifier: str
    severity: str
    applicable: bool
    reason: str
    treatment: str


@dataclass(frozen=True, slots=True)
class ReviewedComponent:
    name: str
    version: str
    advisories: tuple[Advisory, ...]


@dataclass(frozen=True, slots=True)
class Review:
    reviewed: str
    sources: tuple[str, ...]
    components: tuple[ReviewedComponent, ...]


def load_review(root: Path) -> Review:
    path = root / REVIEW_FILE
    try:
        with path.open("rb") as source:
            document = tomllib.load(source)
        if document["version"] != REVIEW_VERSION:
            raise CheckError(f"{path}: unsupported version {document['version']!r}")
        return Review(
            reviewed=str(document["reviewed"]),
            sources=tuple(str(source) for source in document["sources"]),
            components=tuple(_component(entry) for entry in document["component"]),
        )
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise CheckError(f"{path}: the advisory review is malformed: {error}") from error


def review_problems(lock: ToolchainLock, review: Review) -> list[str]:
    reviewed = {component.name: component for component in review.components}
    pinned = {artifact.name: artifact.version for artifact in lock.artifacts}
    pinned |= {component.name: component.version for component in lock.components}
    problems = []
    for name, version in sorted(pinned.items()):
        component = reviewed.get(name)
        if component is None:
            problems.append(f"{name} {version}: no advisory review")
        elif component.version != version:
            problems.append(
                f"{name}: the review covers {component.version} but the lock pins {version}"
            )
        else:
            problems.extend(
                f"{name} {version}: {advisory.identifier} is {advisory.severity}, "
                "applicable and untreated"
                for advisory in component.advisories
                if _blocks(advisory)
            )
    return problems


def _blocks(advisory: Advisory) -> bool:
    return (
        advisory.applicable and advisory.severity in BLOCKING_SEVERITIES and not advisory.treatment
    )


def _component(entry: dict[str, object]) -> ReviewedComponent:
    listed = entry.get("advisory", [])
    if not isinstance(listed, list):
        raise TypeError("the advisories of a component are not a list")
    return ReviewedComponent(
        name=str(entry["name"]),
        version=str(entry["version"]),
        advisories=tuple(_advisory(advisory) for advisory in listed),
    )


def _advisory(entry: dict[str, object]) -> Advisory:
    applicable = entry["applicable"]
    if not isinstance(applicable, bool):
        raise TypeError("applicable must be true or false")
    return Advisory(
        identifier=str(entry["id"]),
        severity=str(entry["severity"]),
        applicable=applicable,
        reason=str(entry["reason"]),
        treatment=str(entry.get("treatment", "")),
    )
