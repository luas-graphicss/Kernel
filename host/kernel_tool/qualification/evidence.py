import json
from pathlib import Path

from kernel_tool.build.native import BuildOutputs
from kernel_tool.outcome import CheckError
from kernel_tool.toolchain.fetch import sha256_file

EVIDENCE_DIRECTORY = "qualification"
VERIFICATION = "verification"
BOOTS = "boots"
SOAK = "soak"
MEASUREMENTS = "measurements"
REPRODUCTION = "reproduction"
ENCODING = "utf-8"


def release_artifacts(outputs: BuildOutputs) -> tuple[Path, ...]:
    return (outputs.kernel, outputs.init_image, outputs.boot_image)


def artifact_identity(outputs: BuildOutputs) -> dict[str, str]:
    return {
        artifact.name: sha256_file(artifact)
        for artifact in release_artifacts(outputs)
        if artifact.is_file()
    }


def evidence_file(outputs: BuildOutputs, name: str) -> Path:
    return outputs.directory / EVIDENCE_DIRECTORY / f"{name}.json"


def write_evidence(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding=ENCODING)


def read_evidence(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding=ENCODING))
    except ValueError as error:
        raise CheckError(f"{path}: the evidence is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise CheckError(f"{path}: the evidence is not a JSON object")
    return document
