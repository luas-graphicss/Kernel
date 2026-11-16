import re

from kernel_tool.scenarios.model import Scenario
from kernel_tool.verification.transcript import KernelTranscript

CORPUS_PREFIX = "corpus:"


def check_transcript(scenario: Scenario, transcript: KernelTranscript) -> list[str]:
    failures = []
    if transcript.status is not scenario.expected_status:
        failures.append(
            f"kernel status is {transcript.status.value}, expected {scenario.expected_status.value}"
        )
    failures.extend(_missing_lines(scenario.expected_lines, transcript.lines))
    failures.extend(
        f"line {line!r} matches the forbidden pattern {pattern!r}"
        for pattern in scenario.forbidden_lines
        for line in transcript.lines
        if re.search(pattern, line)
    )
    return failures


def check_repeats(transcripts: list[tuple[str, ...]]) -> list[str]:
    if all(transcript == transcripts[0] for transcript in transcripts[1:]):
        return []
    return ["repeated boots of the same image produced different transcripts"]


def check_corpus(lines: tuple[str, ...], reference: tuple[str, ...]) -> list[str]:
    reported = tuple(line for line in lines if line.startswith(CORPUS_PREFIX))
    if reported == reference:
        return []
    return [
        "the guest corpus differs from CPython: "
        f"guest reported {list(reported)}, CPython reported {list(reference)}"
    ]


def _missing_lines(patterns: tuple[str, ...], lines: tuple[str, ...]) -> list[str]:
    missing = []
    position = 0
    for pattern in patterns:
        found = next(
            (index for index in range(position, len(lines)) if re.search(pattern, lines[index])),
            None,
        )
        if found is None:
            missing.append(f"no line from position {position} matches {pattern!r}")
        else:
            position = found + 1
    return missing
