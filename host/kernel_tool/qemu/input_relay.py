import os
from dataclasses import dataclass
from typing import IO, Protocol

INPUT_BYTES = 4096


@dataclass(frozen=True, slots=True)
class HeldInput:
    source: int
    released_by: bytes


class OperatorInput(Protocol):
    def hear(self, transcript: bytearray) -> None: ...

    def readable(self) -> list[int]: ...

    def writable(self) -> list[int]: ...

    def read(self) -> None: ...

    def write(self) -> None: ...


class InheritedInput:
    def hear(self, transcript: bytearray) -> None:
        return

    def readable(self) -> list[int]:
        return []

    def writable(self) -> list[int]:
        return []

    def read(self) -> None:
        return

    def write(self) -> None:
        return


class InputRelay:
    def __init__(self, held: HeldInput, emulator_input: IO[bytes]) -> None:
        self._held = held
        self._emulator_input = emulator_input
        self._sink = emulator_input.fileno()
        self._pending = b""
        self._is_released = False
        self._is_open = True
        os.set_blocking(self._sink, False)

    def hear(self, transcript: bytearray) -> None:
        if not self._is_released:
            self._is_released = self._held.released_by in transcript

    def readable(self) -> list[int]:
        if self._is_open and self._is_released and not self._pending:
            return [self._held.source]
        return []

    def writable(self) -> list[int]:
        return [self._sink] if self._pending else []

    def read(self) -> None:
        self._pending = os.read(self._held.source, INPUT_BYTES)
        if not self._pending:
            self._close()

    def write(self) -> None:
        try:
            sent = os.write(self._sink, self._pending)
        except BlockingIOError:
            return
        except BrokenPipeError:
            self._pending = b""
            self._close()
            return
        self._pending = self._pending[sent:]

    def _close(self) -> None:
        self._is_open = False
        self._emulator_input.close()
