import codecs
import os
import re
import select
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from typing import IO

from kernel_tool.outcome import InfrastructureError

COMPLETION = re.compile(
    r"shell: command=(?P<command>\S+) status=(?P<status>ok|failed error=[A-Z_]+)"
)
READ_BYTES = 65536
ENCODING = "utf-8"
CARRIAGE_RETURN = "\r"
LINE_END = "\n"


class GuestSilentError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Reply:
    lines: tuple[str, ...]
    status: str


class ShellOperator:
    def __init__(
        self, emulator: subprocess.Popen[bytes], log: IO[str], forbidden: tuple[str, ...]
    ) -> None:
        if emulator.stdout is None or emulator.stdin is None:
            raise InfrastructureError("the emulator was started without its serial pipes")
        self._output = emulator.stdout.fileno()
        self._input = emulator.stdin
        self._log = log
        self._forbidden = tuple(re.compile(pattern) for pattern in forbidden)
        self._decoder = codecs.getincrementaldecoder(ENCODING)(errors="replace")
        self._partial = ""
        self._unread: deque[str] = deque()
        self.violations: list[str] = []
        self.closed = False

    def await_line(self, pattern: re.Pattern[str], timeout: float) -> list[str]:
        deadline = time.monotonic() + timeout
        heard = []
        while True:
            while self._unread:
                line = self._unread.popleft()
                heard.append(line)
                if pattern.search(line):
                    return heard
            if not self._listen(deadline):
                raise GuestSilentError(
                    f"no line matched {pattern.pattern!r} within {timeout:g} seconds"
                )

    def send(self, text: str) -> None:
        try:
            self._input.write((text + LINE_END).encode(ENCODING))
            self._input.flush()
        except OSError as error:
            raise GuestSilentError(f"the guest stopped reading its console: {error}") from error

    def command(self, text: str, timeout: float) -> Reply:
        self.send(text)
        lines = self.await_line(COMPLETION, timeout)
        completion = COMPLETION.search(lines[-1])
        return Reply(tuple(lines), completion["status"] if completion is not None else "")

    def drain(self, timeout: float) -> list[str]:
        deadline = time.monotonic() + timeout
        while self._listen(deadline):
            pass
        if not self.closed:
            raise GuestSilentError(f"the guest did not stop within {timeout:g} seconds")
        if self._partial:
            self._hear(self._partial)
            self._partial = ""
        remaining = list(self._unread)
        self._unread.clear()
        return remaining

    def _listen(self, deadline: float) -> bool:
        remaining = deadline - time.monotonic()
        if self.closed or remaining <= 0:
            return False
        if not select.select([self._output], [], [], remaining)[0]:
            return False
        chunk = os.read(self._output, READ_BYTES)
        if not chunk:
            self.closed = True
            return False
        text = self._partial + self._decoder.decode(chunk).replace(CARRIAGE_RETURN, "")
        *complete, self._partial = text.split(LINE_END)
        for line in complete:
            self._hear(line)
        return True

    def _hear(self, line: str) -> None:
        if not line.strip():
            return
        self._log.write(line + LINE_END)
        if any(pattern.search(line) for pattern in self._forbidden):
            self.violations.append(line)
        self._unread.append(line)
