import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kernel_tool.fuzzing.model import Family, Target, TargetRun
from kernel_tool.fuzzing.registry import targets_of
from kernel_tool.outcome import CheckError

LEDGER_FILE = "ledger.json"
LEDGER_VERSION = 1
SOURCE_SUFFIXES = (".py", ".c", ".h")
SECONDS_PER_HOUR = 3600


@dataclass(frozen=True, slots=True)
class TargetRecord:
    digest: str
    seconds: float
    executions: int
    sessions: int
    population: int
    open_findings: int


@dataclass(frozen=True, slots=True)
class FamilyEvidence:
    family: Family
    hours: float
    executions: int
    open_findings: int
    targets: dict[str, TargetRecord]


def target_digest(root: Path, target: Target) -> str:
    digest = hashlib.sha256()
    for source in target.sources:
        for file in _source_files(root / source):
            digest.update(file.relative_to(root).as_posix().encode("utf-8"))
            digest.update(file.read_bytes())
    return digest.hexdigest()


def read_ledger(directory: Path) -> dict[str, TargetRecord]:
    path = directory / LEDGER_FILE
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["version"] != LEDGER_VERSION:
            raise CheckError(f"{path}: unsupported ledger version {document['version']!r}")
        return {key: TargetRecord(**record) for key, record in document["targets"].items()}
    except (KeyError, TypeError, ValueError) as error:
        raise CheckError(f"{path}: the fuzzing ledger is malformed: {error}") from error


def record_runs(directory: Path, root: Path, runs: list[tuple[Target, TargetRun]]) -> None:
    records = read_ledger(directory)
    for target, run in runs:
        key = ledger_key(target)
        digest = target_digest(root, target)
        earlier = records.get(key)
        if earlier is None or earlier.digest != digest:
            earlier = TargetRecord(digest, 0.0, 0, 0, 0, 0)
        records[key] = TargetRecord(
            digest=digest,
            seconds=earlier.seconds + run.seconds,
            executions=earlier.executions + run.executions,
            sessions=earlier.sessions + 1,
            population=run.population,
            open_findings=len(run.findings),
        )
    document = {
        "version": LEDGER_VERSION,
        "targets": {key: asdict(records[key]) for key in sorted(records)},
    }
    directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    (directory / LEDGER_FILE).write_text(text, encoding="utf-8")


def family_evidence(directory: Path, root: Path, family: Family) -> FamilyEvidence:
    records = read_ledger(directory)
    current = {}
    for target in targets_of(family):
        record = records.get(ledger_key(target))
        if record is not None and record.digest == target_digest(root, target):
            current[target.name] = record
    return FamilyEvidence(
        family=family,
        hours=sum(record.seconds for record in current.values()) / SECONDS_PER_HOUR,
        executions=sum(record.executions for record in current.values()),
        open_findings=sum(record.open_findings for record in current.values()),
        targets=current,
    )


def ledger_key(target: Target) -> str:
    return f"{target.family.value}/{target.name}"


def _source_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if not source.is_dir():
        raise CheckError(f"the fuzzing target source {source} does not exist")
    return sorted(
        file for file in source.rglob("*") if file.is_file() and file.suffix in SOURCE_SUFFIXES
    )
