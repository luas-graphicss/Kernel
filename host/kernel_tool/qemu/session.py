import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass

from kernel_tool.outcome import InfrastructureError

SERIAL_READY = b"policy: admitted=init"
READ_BYTES = 65536


@dataclass(frozen=True, slots=True)
class SessionResult:
    exit_code: int | None
    transcript: str
    emulator_messages: str
    duration_seconds: float

    @property
    def timed_out(self) -> bool:
        return self.exit_code is None


def run_session(
    command: list[str], deadline_seconds: float, serial_input: bytes | None = None
) -> SessionResult:
    started = time.monotonic()
    try:
        if serial_input is None:
            exit_code, transcript, messages = _run_silent(command, deadline_seconds)
        else:
            exit_code, transcript, messages = _run_typed(command, deadline_seconds, serial_input)
    except OSError as error:
        raise InfrastructureError(f"cannot start the emulator: {error}") from error
    return SessionResult(
        exit_code=exit_code,
        transcript=_decode(transcript),
        emulator_messages=_decode(messages),
        duration_seconds=time.monotonic() - started,
    )


def _run_silent(
    command: list[str], deadline_seconds: float
) -> tuple[int | None, bytes | None, bytes | None]:
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=deadline_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return None, expired.stdout, expired.stderr
    return completed.returncode, completed.stdout, completed.stderr


def _run_typed(
    command: list[str], deadline_seconds: float, serial_input: bytes
) -> tuple[int | None, bytes, bytes]:
    transcript = bytearray()
    with (
        tempfile.TemporaryFile() as messages,
        subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=messages
        ) as emulator,
    ):
        typist = threading.Thread(
            target=_type_when_ready, args=(emulator, serial_input, transcript)
        )
        typist.start()
        exit_code: int | None = None
        try:
            exit_code = emulator.wait(timeout=deadline_seconds)
        except subprocess.TimeoutExpired:
            emulator.kill()
            emulator.wait()
        typist.join()
        messages.seek(0)
        return exit_code, bytes(transcript), messages.read()


def _type_when_ready(
    emulator: subprocess.Popen[bytes], serial_input: bytes, transcript: bytearray
) -> None:
    if emulator.stdout is None or emulator.stdin is None:
        return
    typed = False
    while chunk := os.read(emulator.stdout.fileno(), READ_BYTES):
        transcript.extend(chunk)
        if not typed and SERIAL_READY in transcript:
            typed = True
            _type(emulator, serial_input)


def _type(emulator: subprocess.Popen[bytes], serial_input: bytes) -> None:
    if emulator.stdin is None:
        return
    try:
        emulator.stdin.write(serial_input)
        emulator.stdin.close()
    except BrokenPipeError:
        return


def _decode(output: bytes | None) -> str:
    if output is None:
        return ""
    return output.decode("utf-8", errors="replace").replace("\r\n", "\n")
