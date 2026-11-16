from dataclasses import asdict, dataclass
from pathlib import Path

from kernel_tool.faults.matrix import run_matrix
from kernel_tool.faults.sequences import run_sequence
from kernel_tool.faults.trace import check_trace
from kernel_tool.faults.write_log import read_write_log
from kernel_tool.outcome import CheckError
from kernel_tool.scenarios.disks import (
    DATA_BLOCKS,
    DATA_VOLUME,
    VOLUME_REPORT,
    write_log_file,
)
from kernel_tool.storage.volumes import create_image

REPORTED_FAILURES = 20


@dataclass(frozen=True, slots=True)
class Stage:
    name: str
    counts: dict[str, int]
    failures: tuple[str, ...]
    evidence: object

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_document(self) -> dict[str, object]:
        return asdict(self) | {"passed": self.passed}


def format_stage(stage: Stage) -> str:
    verdict = "PASS" if stage.passed else "FAIL"
    counts = " ".join(f"{name}={value}" for name, value in stage.counts.items())
    lines = [f"{verdict} {stage.name} {counts}"]
    lines.extend(f"  failure: {failure}" for failure in stage.failures[:REPORTED_FAILURES])
    return "\n".join(lines) + "\n"


def matrix_stage() -> Stage:
    points = run_matrix()
    failures = tuple(
        f"{point.transaction} after {point.after}: {failure}"
        for point in points
        for failure in point.failures
    )
    counts = {
        "transactions": len({point.transaction for point in points}),
        "crash-points": len(points),
        "images": sum(point.images for point in points),
    }
    return Stage("crash-matrix", counts, failures, [asdict(point) for point in points])


def sequences_stage(count: int, first_seed: int) -> Stage:
    if count < 1:
        raise CheckError("the number of sequences must be positive")
    results = [run_sequence(seed) for seed in range(first_seed, first_seed + count)]
    failures = tuple(failure for result in results for failure in result.failures)
    counts = {
        "sequences": count,
        "first-seed": first_seed,
        "commits": sum(result.commits for result in results),
        "images": sum(result.images for result in results),
    }
    evidence = {
        "first_seed": first_seed,
        "last_seed": first_seed + count - 1,
        "failed_seeds": sorted({result.seed for result in results if result.failures}),
    }
    return Stage("crash-sequences", counts, failures, evidence)


def trace_stage(directory: Path, transcript: tuple[str, ...]) -> Stage:
    log = write_log_file(directory)
    if not log.is_file():
        raise CheckError(f"{log} does not exist; the traced scenario did not run")
    reported = [
        (int(match.group(1)), match.group(2))
        for match in map(VOLUME_REPORT.match, transcript)
        if match is not None
    ]
    events = read_write_log(log.read_bytes())
    result = check_trace(create_image(DATA_BLOCKS, DATA_VOLUME), events, reported)
    counts = {
        "events": len(result.events),
        "generations": len(result.generations),
        "images": result.images,
    }
    return Stage("flush-trace-replay", counts, result.failures, asdict(result))
