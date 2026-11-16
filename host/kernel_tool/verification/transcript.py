from dataclasses import dataclass
from enum import StrEnum

KERNEL_PREFIX = "boot:"
STATUS_PREFIX = "kernel: status="


class KernelStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class KernelTranscript:
    lines: tuple[str, ...]
    status: KernelStatus


def read_transcript(serial_output: str) -> KernelTranscript:
    lines = [line for line in serial_output.splitlines() if line.strip()]
    first = next(
        (index for index, line in enumerate(lines) if line.startswith(KERNEL_PREFIX)), None
    )
    kernel_lines = tuple(lines[first:]) if first is not None else ()
    return KernelTranscript(lines=kernel_lines, status=_status(kernel_lines))


def _status(kernel_lines: tuple[str, ...]) -> KernelStatus:
    reported = [line for line in kernel_lines if line.startswith(STATUS_PREFIX)]
    if not reported:
        return KernelStatus.MISSING
    if len(reported) > 1 or kernel_lines[-1] != reported[0]:
        return KernelStatus.AMBIGUOUS
    value = reported[0].removeprefix(STATUS_PREFIX)
    if value == KernelStatus.OK:
        return KernelStatus.OK
    if value == KernelStatus.FAILED:
        return KernelStatus.FAILED
    return KernelStatus.AMBIGUOUS
