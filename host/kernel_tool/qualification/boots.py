import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass

from kernel_tool.scenarios.model import Scenario
from kernel_tool.scenarios.runner import SuiteContext, run_scenario

ENCODING = "utf-8"


@dataclass(frozen=True, slots=True)
class BootRecord:
    number: int
    passed: bool
    seconds: float
    transcript_sha256: str
    failures: tuple[str, ...]
    transcript: tuple[str, ...]


def boot_repeatedly(
    scenario: Scenario,
    context: SuiteContext,
    count: int,
    records: list[BootRecord],
    progress: Callable[[BootRecord], None],
) -> None:
    for number in range(len(records) + 1, count + 1):
        result = run_scenario(scenario, context)
        digest = hashlib.sha256("\n".join(result.transcript).encode(ENCODING)).hexdigest()
        record = BootRecord(
            number=number,
            passed=result.passed,
            seconds=result.duration_seconds,
            transcript_sha256=digest,
            failures=result.failures,
            transcript=() if result.passed else result.transcript,
        )
        records.append(record)
        progress(record)


def boots_document(
    profile: str,
    artifacts: dict[str, str],
    requested: int,
    records: list[BootRecord],
) -> dict[str, object]:
    failed = [record.number for record in records if not record.passed]
    seconds = sorted(record.seconds for record in records)
    return {
        "profile": profile,
        "artifacts": artifacts,
        "requested": requested,
        "completed": len(records),
        "failed": failed,
        "passed": len(records) == requested and not failed,
        "distinct_transcripts": len({record.transcript_sha256 for record in records}),
        "fastest_seconds": seconds[0] if seconds else None,
        "slowest_seconds": seconds[-1] if seconds else None,
        "boots": [asdict(record) for record in records],
    }
