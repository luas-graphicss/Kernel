import codecs
import os
import re
import selectors
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass

from kernel_tool.outcome import InfrastructureError
from kernel_tool.qemu.session import SessionResult

READ_BYTES = 65536
POLL_SECONDS = 0.05
ENCODING = "utf-8"
CARRIAGE_RETURN = "\r"


@dataclass(frozen=True, slots=True)
class Exchange:
    awaited: str
    typed: str = ""
    action: Callable[[], None] | None = None


class Conversation:
    def __init__(self, exchanges: tuple[Exchange, ...]) -> None:
        self._pending = list(exchanges)
        self._decoder = codecs.getincrementaldecoder(ENCODING)(errors="replace")
        self._heard = ""
        self._cursor = 0

    @property
    def unanswered(self) -> tuple[str, ...]:
        return tuple(exchange.awaited for exchange in self._pending)

    @property
    def transcript(self) -> str:
        return self._heard

    def hear(self, chunk: bytes) -> list[Exchange]:
        self._heard += self._decoder.decode(chunk).replace(CARRIAGE_RETURN, "")
        answered = []
        while self._pending:
            awaited = re.compile(self._pending[0].awaited, re.MULTILINE)
            match = awaited.search(self._heard, self._cursor)
            if match is None:
                break
            self._cursor = match.end()
            answered.append(self._pending.pop(0))
        return answered


@dataclass(frozen=True, slots=True)
class DialogueResult:
    session: SessionResult
    unanswered: tuple[str, ...]


def run_dialogue(
    command: list[str], deadline_seconds: float, exchanges: tuple[Exchange, ...]
) -> DialogueResult:
    started = time.monotonic()
    conversation = Conversation(exchanges)
    try:
        with (
            tempfile.TemporaryFile() as messages,
            subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=messages
            ) as emulator,
        ):
            exit_code = _converse(emulator, conversation, started + deadline_seconds)
            messages.seek(0)
            emulator_messages = messages.read()
    except OSError as error:
        raise InfrastructureError(f"cannot start the emulator: {error}") from error
    session = SessionResult(
        exit_code=exit_code,
        transcript=conversation.transcript,
        emulator_messages=emulator_messages.decode(ENCODING, errors="replace"),
        duration_seconds=time.monotonic() - started,
    )
    return DialogueResult(session, conversation.unanswered)


def _converse(
    emulator: subprocess.Popen[bytes], conversation: Conversation, deadline: float
) -> int | None:
    if emulator.stdout is None or emulator.stdin is None:
        raise InfrastructureError("the emulator was started without its serial pipes")
    output = emulator.stdout.fileno()
    with selectors.DefaultSelector() as selector:
        selector.register(output, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if selector.select(POLL_SECONDS):
                chunk = os.read(output, READ_BYTES)
                if not chunk:
                    break
                for exchange in conversation.hear(chunk):
                    _answer(emulator, exchange)
    try:
        return emulator.wait(timeout=max(deadline - time.monotonic(), POLL_SECONDS))
    except subprocess.TimeoutExpired:
        emulator.kill()
        emulator.wait()
        return None


def _answer(emulator: subprocess.Popen[bytes], exchange: Exchange) -> None:
    if exchange.action is not None:
        exchange.action()
    if not exchange.typed or emulator.stdin is None:
        return
    try:
        emulator.stdin.write(exchange.typed.encode(ENCODING))
        emulator.stdin.flush()
    except BrokenPipeError:
        return
