import io
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from kernel_tool.qemu.operator import GuestSilentError, ShellOperator
from kernel_tool.qualification.soak import (
    FREE_FRAMES,
    ROUND_DURATION,
    WARM_UP_ROUNDS,
    RoundSample,
    analyze,
    collector_report,
    run_session,
    shutdown_failures,
    soak_document,
)

GUEST = [sys.executable, str(Path(__file__).parent / "doubles" / "guest_shell.py")]
READY = re.compile(r"shell: ready$")
FORBIDDEN = (r"trap: ",)
PATIENCE_SECONDS = 20.0
SOAK_SECONDS = 0.4


@contextmanager
def guest(log: io.StringIO) -> Iterator[ShellOperator]:
    with subprocess.Popen(GUEST, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as emulator:
        shell = ShellOperator(emulator, log, FORBIDDEN)
        shell.await_line(READY, PATIENCE_SECONDS)
        try:
            yield shell
        finally:
            emulator.kill()


def ignore(_sample: RoundSample) -> None:
    return None


def test_a_command_returns_what_the_guest_said_and_how_it_ended() -> None:
    log = io.StringIO()
    with guest(log) as shell:
        launched = shell.command("run boot/apps/counter.py", PATIENCE_SECONDS)
        failed = shell.command("fail", PATIENCE_SECONDS)

    assert launched.status == "ok"
    assert launched.lines[0] == "run: application=1 program=boot/apps/counter.py"
    assert failed.status == "failed error=NOT_FOUND"
    assert "shell: ready\n" in log.getvalue()


def test_a_forbidden_line_is_noticed_wherever_it_is_printed() -> None:
    with guest(io.StringIO()) as shell:
        shell.command("trap", PATIENCE_SECONDS)

        assert shell.violations == ["kernel> trap: cause=13"]


def test_a_guest_that_stops_answering_is_not_waited_for_forever() -> None:
    with guest(io.StringIO()) as shell, pytest.raises(GuestSilentError, match="no line matched"):
        shell.command("silence", 0.2)


def test_the_last_lines_are_read_until_the_guest_closes_its_console() -> None:
    with guest(io.StringIO()) as shell:
        shell.send("shutdown")
        final_lines = shell.drain(PATIENCE_SECONDS)

    assert final_lines[-1] == "kernel: status=ok"
    assert shutdown_failures(final_lines) == []
    assert shutdown_failures(final_lines[:-1]) == ["the kernel did not end with status ok"]


def test_a_soak_keeps_one_boot_loaded_and_samples_every_round(tmp_path: Path) -> None:
    session = run_session(GUEST, SOAK_SECONDS, tmp_path / "soak.log", True, ignore)
    trends = analyze(session.samples)
    document = soak_document(session, trends, list(session.failures))

    assert session.failures == ()
    assert len(session.samples) > WARM_UP_ROUNDS
    assert [sample.number for sample in session.samples[:3]] == [1, 2, 3]
    assert session.samples[0].counters[FREE_FRAMES] == 5000
    assert not any(trend.persistent for trend in trends.values())
    assert trends[ROUND_DURATION].samples == len(session.samples) - WARM_UP_ROUNDS - 1
    assert document["passed"] is True
    assert collector_report(session.final_lines)["collections"] == 2
    assert "fetch.py" in (tmp_path / "soak.log").read_text(encoding="utf-8")


def test_a_soak_without_the_network_never_asks_for_it(tmp_path: Path) -> None:
    session = run_session(GUEST, SOAK_SECONDS, tmp_path / "soak.log", False, ignore)

    assert session.failures == ()
    assert "fetch.py" not in (tmp_path / "soak.log").read_text(encoding="utf-8")


def test_frames_that_never_come_back_are_reported_as_a_decline(tmp_path: Path) -> None:
    session = run_session([*GUEST, "--leak"], SOAK_SECONDS, tmp_path / "soak.log", True, ignore)

    trends = analyze(session.samples)

    assert session.failures == ()
    assert trends[FREE_FRAMES].persistent
    assert trends[FREE_FRAMES].later_extreme < trends[FREE_FRAMES].earlier_extreme


def test_a_soak_that_ends_inside_its_warm_up_does_not_pass(tmp_path: Path) -> None:
    session = run_session(GUEST, 0.0, tmp_path / "soak.log", True, ignore)

    assert session.samples == ()
    assert soak_document(session, analyze(session.samples), [])["passed"] is False
