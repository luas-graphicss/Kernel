import os
import select
import subprocess
import sys
import tempfile
import time

from kernel_tool.outcome import InfrastructureError
from kernel_tool.qemu.input_relay import HeldInput, InheritedInput, InputRelay, OperatorInput
from kernel_tool.qemu.session import SessionResult

READ_BYTES = 65536
POLL_SECONDS = 0.1
STOP_TIMEOUT_SECONDS = 5.0
ENCODING = "utf-8"


def run_attached(
    command: list[str], deadline_seconds: float | None, held_input: HeldInput | None = None
) -> SessionResult:
    started = time.monotonic()
    deadline = None if deadline_seconds is None else started + deadline_seconds
    transcript = bytearray()
    emulator_input = None if held_input is None else subprocess.PIPE
    try:
        with (
            tempfile.TemporaryFile() as messages,
            subprocess.Popen(
                command, stdin=emulator_input, stdout=subprocess.PIPE, stderr=messages
            ) as emulator,
        ):
            try:
                exit_code = _relay(
                    emulator, transcript, deadline, _operator_input(emulator, held_input)
                )
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


def _operator_input(
    emulator: subprocess.Popen[bytes], held_input: HeldInput | None
) -> OperatorInput:
    if held_input is None or emulator.stdin is None:
        return InheritedInput()
    return InputRelay(held_input, emulator.stdin)


def _relay(
    emulator: subprocess.Popen[bytes],
    transcript: bytearray,
    deadline: float | None,
    operator: OperatorInput,
) -> int | None:
    if emulator.stdout is None:
        raise InfrastructureError("the emulator was started without its serial output")
    output = emulator.stdout.fileno()
    while deadline is None or time.monotonic() < deadline:
        sources = operator.readable()
        readable, writable, _ = select.select(
            [output, *sources], operator.writable(), [], POLL_SECONDS
        )
        if writable:
            operator.write()
        if any(source in readable for source in sources):
            operator.read()
        if output not in readable:
            continue
        chunk = os.read(output, READ_BYTES)
        if not chunk:
            return emulator.wait()
        transcript.extend(chunk)
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
        operator.hear(transcript)
    _stop(emulator)
    return None


def _stop(emulator: subprocess.Popen[bytes]) -> None:
    emulator.terminate()
    try:
        emulator.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        emulator.kill()
        emulator.wait()
