import json
from dataclasses import asdict
from pathlib import Path

from kernel_tool.scenarios.runner import ScenarioResult


def format_result(result: ScenarioResult) -> str:
    verdict = "PASS" if result.passed else "FAIL"
    lines = [
        f"{verdict} {result.name} runs={result.runs} seconds={result.duration_seconds:.1f} "
        f"image={result.image} sha256={result.image_sha256}"
    ]
    if result.network is not None:
        lines.append(
            f"  network: peer={result.network.peer_stack!r} "
            f"frames={result.network.captured_frames} capture={result.network.capture}"
        )
    if not result.passed:
        lines.extend(f"  failure: {failure}" for failure in result.failures)
        lines.extend(f"  | {line}" for line in result.transcript)
    return "\n".join(lines) + "\n"


def suite_document(suite: str, profile: str, results: list[ScenarioResult]) -> dict[str, object]:
    return {
        "suite": suite,
        "profile": profile,
        "passed": all(result.passed for result in results),
        "scenarios": [asdict(result) | {"passed": result.passed} for result in results],
    }


def write_document(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
