import sys

import pytest

from kernel_tool.outcome import InfrastructureError
from kernel_tool.qemu.console import run_attached

PRINTER = "print('boot: hart=0'); print('kernel: status=ok')"
SLEEPER = "import time; print('boot: hart=0', flush=True); time.sleep(60)"


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
