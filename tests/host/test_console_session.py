import os
import sys
from pathlib import Path

import pytest

from kernel_tool.outcome import InfrastructureError
from kernel_tool.qemu.console import run_attached
from kernel_tool.qemu.input_relay import HeldInput

PRINTER = "print('boot: hart=0'); print('kernel: status=ok')"
SLEEPER = "import time; print('boot: hart=0', flush=True); time.sleep(60)"
READY = b"shell: ready"
EARLY_INPUT_LOST = """
import os
import sys
import time

print('boot: hart=0', flush=True)
time.sleep(0.3)
os.set_blocking(0, False)
try:
    lost = os.read(0, 4096)
except BlockingIOError:
    lost = b''
os.set_blocking(0, True)
print('shell: ready', flush=True)
print(f'lost={len(lost)} heard={sys.stdin.readline().strip()}', flush=True)
"""
COUNTS_UNTIL_INPUT_ENDS = """
import sys

print('shell: ready', flush=True)
print(f'lines={len(sys.stdin.readlines())}', flush=True)
"""


def typed(text: bytes) -> int:
    source, sink = os.pipe()
    os.write(sink, text)
    os.close(sink)
    return source


def test_what_the_guest_prints_is_shown_and_kept(capfdbinary: pytest.CaptureFixture[bytes]) -> None:
    result = run_attached([sys.executable, "-c", PRINTER], None)

    assert result.exit_code == 0
    assert result.transcript == "boot: hart=0\nkernel: status=ok\n"
    assert capfdbinary.readouterr().out == b"boot: hart=0\nkernel: status=ok\n"


def test_a_session_past_its_deadline_is_stopped() -> None:
    result = run_attached([sys.executable, "-c", SLEEPER], 1.0)

    assert result.timed_out
    assert result.transcript == "boot: hart=0\n"


def test_an_emulator_that_cannot_start_is_an_infrastructure_error() -> None:
    with pytest.raises(InfrastructureError, match="cannot start the emulator"):
        run_attached(["/nonexistent/emulator"], None)


def test_input_sent_before_the_shell_is_ready_is_held_and_arrives_whole() -> None:
    source = typed(b"shutdown\n")
    try:
        result = run_attached(
            [sys.executable, "-c", EARLY_INPUT_LOST], 30.0, HeldInput(source, READY)
        )
    finally:
        os.close(source)

    assert result.exit_code == 0
    assert result.transcript.endswith("shell: ready\nlost=0 heard=shutdown\n")


def test_the_emulator_sees_its_input_end_when_the_held_input_ends() -> None:
    source = typed(b"ls\nshutdown\n")
    try:
        result = run_attached(
            [sys.executable, "-c", COUNTS_UNTIL_INPUT_ENDS], 30.0, HeldInput(source, READY)
        )
    finally:
        os.close(source)

    assert result.exit_code == 0
    assert result.transcript == "shell: ready\nlines=2\n"


def test_input_redirected_from_a_file_is_held_like_a_pipe(tmp_path: Path) -> None:
    script = tmp_path / "commands"
    script.write_bytes(b"shutdown\n")
    with script.open("rb") as commands:
        result = run_attached(
            [sys.executable, "-c", EARLY_INPUT_LOST], 30.0, HeldInput(commands.fileno(), READY)
        )

    assert result.exit_code == 0
    assert result.transcript.endswith("lost=0 heard=shutdown\n")
