import pytest

from kernel_apps.shell.interpreter import serve_line
from kernel_protocol.errors.codes import CANCELLED, MESSAGE_TOO_LARGE, KernelError

REFUSED = "the test refuses this request"


class Terminal:
    def __init__(self, entered: list[str | KernelError]) -> None:
        self._entered = entered
        self.written: list[str] = []

    def read_line(self) -> str:
        line = self._entered.pop(0)
        if isinstance(line, KernelError):
            raise line
        return line

    def write(self, text: str) -> None:
        self.written.append(text)

    def failed(self, error: KernelError) -> None:
        return


def test_a_line_the_console_refused_as_too_long_is_reported_and_not_run() -> None:
    terminal = Terminal([KernelError(MESSAGE_TOO_LARGE, REFUSED), "frobnicate"])

    serve_line(terminal)
    serve_line(terminal)

    assert terminal.written == [
        "shell: command=none status=failed error=MESSAGE_TOO_LARGE",
        "shell: command=frobnicate status=failed error=UNSUPPORTED",
    ]


def test_any_other_console_failure_ends_the_shell() -> None:
    terminal = Terminal([KernelError(CANCELLED, REFUSED)])

    with pytest.raises(KernelError) as failure:
        serve_line(terminal)

    assert failure.value.code == CANCELLED
    assert terminal.written == []
