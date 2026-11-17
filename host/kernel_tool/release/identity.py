import re
import tomllib
from pathlib import Path

from kernel_tool.outcome import CheckError

PROJECT_FILE = "pyproject.toml"
VERSION = re.compile(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")


def project_metadata(root: Path) -> dict[str, object]:
    path = root / PROJECT_FILE
    try:
        with path.open("rb") as source:
            project = tomllib.load(source)["project"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        raise CheckError(f"{path}: cannot read the project table: {error}") from error
    if not isinstance(project, dict):
        raise CheckError(f"{path}: the project table is malformed")
    return project


def project_version(root: Path) -> str:
    version = project_metadata(root).get("version")
    if not isinstance(version, str) or VERSION.fullmatch(version) is None:
        raise CheckError(f"{root / PROJECT_FILE}: the project version {version!r} is not valid")
    return version


def project_license(root: Path) -> str:
    license_expression = project_metadata(root).get("license")
    if not isinstance(license_expression, str) or not license_expression:
        raise CheckError(f"{root / PROJECT_FILE}: the project states no license expression")
    return license_expression


def project_repository(root: Path) -> str:
    urls = project_metadata(root).get("urls")
    repository = urls.get("Repository") if isinstance(urls, dict) else None
    if not isinstance(repository, str) or not repository.startswith("https://"):
        raise CheckError(f"{root / PROJECT_FILE}: the project states no repository address")
    return repository.rstrip("/")
