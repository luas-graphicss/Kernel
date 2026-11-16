import subprocess
import time
from dataclasses import dataclass

from kernel_tool.outcome import InfrastructureError


@dataclass(frozen=True, slots=True)
class SessionResult:
    exit_code: int | None
    transcript: str
    emulator_messages: str
    duration_seconds: float

    @property
    def timed_out(self) -> bool:
        return self.exit_code is None


def run_session(command: list[str], deadline_seconds: float) -> SessionResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=deadline_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return SessionResult(
            exit_code=None,
            transcript=_decode(expired.stdout),
            emulator_messages=_decode(expired.stderr),
            duration_seconds=time.monotonic() - started,
        )
    except OSError as error:
        raise InfrastructureError(f"cannot start the emulator: {error}") from error

    return SessionResult(
        exit_code=completed.returncode,
        transcript=_decode(completed.stdout),
        emulator_messages=_decode(completed.stderr),
        duration_seconds=time.monotonic() - started,
    )


def _decode(output: bytes | None) -> str:
    if output is None:
        return ""
    return output.decode("utf-8", errors="replace").replace("\r\n", "\n")
