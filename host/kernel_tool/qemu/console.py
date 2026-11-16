import os
import selectors
import subprocess
import sys
import tempfile
import time

from kernel_tool.outcome import InfrastructureError
from kernel_tool.qemu.session import SessionResult

READ_BYTES = 65536
POLL_SECONDS = 0.1
STOP_TIMEOUT_SECONDS = 5.0
ENCODING = "utf-8"


def run_attached(command: list[str], deadline_seconds: float | None) -> SessionResult:
    started = time.monotonic()
    deadline = None if deadline_seconds is None else started + deadline_seconds
    transcript = bytearray()
    try:
        with (
            tempfile.TemporaryFile() as messages,
            subprocess.Popen(command, stdout=subprocess.PIPE, stderr=messages) as emulator,
        ):
            try:
                exit_code = _relay(emulator, transcript, deadline)
            except KeyboardInterrupt:
                _stop(emulator)
                raise
            messages.seek(0)
            emulator_messages = messages.read()
    except OSError as error:
        raise InfrastructureError(f"cannot start the emulator: {error}") from error
    return SessionResult(
        exit_code=exit_code,
        transcript=transcript.decode(ENCODING, errors="replace").replace("\r\n", "\n"),
        emulator_messages=emulator_messages.decode(ENCODING, errors="replace"),
        duration_seconds=time.monotonic() - started,
    )


def _relay(
    emulator: subprocess.Popen[bytes], transcript: bytearray, deadline: float | None
) -> int | None:
    if emulator.stdout is None:
        raise InfrastructureError("the emulator was started without its serial output")
    output = emulator.stdout.fileno()
    with selectors.DefaultSelector() as selector:
        selector.register(output, selectors.EVENT_READ)
        while deadline is None or time.monotonic() < deadline:
            if not selector.select(POLL_SECONDS):
                continue
            chunk = os.read(output, READ_BYTES)
            if not chunk:
                return emulator.wait()
            transcript.extend(chunk)
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    _stop(emulator)
    return None


def _stop(emulator: subprocess.Popen[bytes]) -> None:
    emulator.terminate()
    try:
        emulator.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        emulator.kill()
        emulator.wait()
