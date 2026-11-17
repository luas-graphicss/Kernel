import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path

from kernel_tool.network.plan import GREETING_PORT, PEER_ADDRESS
from kernel_tool.outcome import InfrastructureError
from kernel_tool.qemu.operator import GuestSilentError, Reply, ShellOperator
from kernel_tool.qualification.measurements import COLLECTOR
from kernel_tool.qualification.trends import Trend, decline, growth, slowdown
from kernel_tool.scenarios.guest_program import CLEAN_EXIT
from kernel_tool.scenarios.shell import SHELL_READY, SYSTEM_FORBIDDEN
from kernel_tool.verification.transcript import STATUS_PREFIX, KernelStatus

BOOT_SECONDS = 120.0
COMMAND_SECONDS = 60.0
SHUTDOWN_SECONDS = 120.0
WAIT_SECONDS = 30
NOTE_FILES = 8
WARM_UP_ROUNDS = 8
TOLERATED_SLOWDOWN = 1.5
FREE_FRAMES = "frames-free"
GROWING_COUNTERS = ("processes", "objects", "capabilities", "endpoints", "buffers", "ipc-bytes")
ROUND_DURATION = "round-duration-us"
LAUNCHED = re.compile(r"run: application=(\d+) ")
MEMORY_FIELD = re.compile(r"([a-z-]+)=(\d+)")
MEMORY_LINE = "mem: "
PULSE = re.compile(r"pulse: clock-us=(\d+)")
NOT_A_DIGIT = r"(?!\d)"
FORBIDDEN = tuple(pattern.removeprefix("^") for pattern in SYSTEM_FORBIDDEN)
SHUTDOWN_COMMAND = "shutdown"
OK = "ok"
ENCODING = "utf-8"


class RoundFailedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RoundSample:
    number: int
    guest_clock_us: int
    counters: dict[str, int]


@dataclass(frozen=True, slots=True)
class SoakSession:
    seconds: float
    samples: tuple[RoundSample, ...]
    failures: tuple[str, ...]
    final_lines: tuple[str, ...]


class Round:
    def __init__(self, shell: ShellOperator, number: int) -> None:
        self._shell = shell
        self._number = number
        self._lines: list[str] = []

    def succeed(self, command: str) -> Reply:
        reply = self._shell.command(command, COMMAND_SECONDS)
        self._lines.extend(reply.lines)
        if reply.status != OK:
            raise RoundFailedError(
                f"round {self._number}: {command!r} ended with status {reply.status}"
            )
        return reply

    def launch(self, program: str) -> int:
        reply = self.succeed("run " + program)
        for line in reply.lines:
            launched = LAUNCHED.search(line)
            if launched is not None:
                return int(launched[1])
        raise RoundFailedError(f"round {self._number}: {program} was given no application number")

    def finish(self, application: int, reason: str, value: int) -> None:
        reply = self.succeed(f"wait {application} {WAIT_SECONDS}")
        expected = f"wait: application={application} reason={reason} value={value}"
        reported = re.compile(re.escape(expected) + NOT_A_DIGIT)
        if not any(reported.search(line) for line in reply.lines):
            raise RoundFailedError(f"round {self._number}: the guest did not report {expected!r}")

    def stop(self, application: int) -> None:
        self.succeed(f"kill {application}")
        self.finish(application, "killed", 0)

    def observed(self, pattern: re.Pattern[str]) -> re.Match[str]:
        for line in self._lines:
            found = pattern.search(line)
            if found is not None:
                return found
        raise RoundFailedError(f"round {self._number}: nothing matched {pattern.pattern!r}")

    def counters(self) -> dict[str, int]:
        reply = self.succeed("mem")
        return {
            field[1]: int(field[2])
            for line in reply.lines
            if MEMORY_LINE in line
            for field in MEMORY_FIELD.finditer(line.partition(MEMORY_LINE)[2])
        }


def run_round(shell: ShellOperator, number: int, with_network: bool) -> RoundSample:
    current = Round(shell, number)
    note = f"data/soak/note-{number % NOTE_FILES}"
    current.succeed(f"write {note} soak round {number}")
    current.finish(current.launch(f"boot/apps/wordcount.py {note}"), "exit", 0)
    if with_network:
        fetch = f"boot/apps/fetch.py {PEER_ADDRESS} {GREETING_PORT} data/soak/greeting"
        current.finish(current.launch(fetch), "exit", 0)
        current.succeed(f"ping {PEER_ADDRESS} 1")
    current.finish(current.launch("boot/apps/hog.py"), "exit", 1)
    spinner = current.launch("boot/apps/spin.py")
    chatter = current.launch("boot/apps/chatter.py tmp/soak-chatter")
    current.finish(current.launch("boot/apps/pulse.py"), "exit", 0)
    current.stop(spinner)
    current.stop(chatter)
    current.succeed("sync")
    clock = int(current.observed(PULSE)[1])
    return RoundSample(number, clock, current.counters())


def run_session(
    command: list[str],
    budget_seconds: float,
    log: Path,
    with_network: bool,
    progress: Callable[[RoundSample], None],
) -> SoakSession:
    started = time.monotonic()
    samples: list[RoundSample] = []
    failures: list[str] = []
    final_lines: list[str] = []
    try:
        with (
            log.open("w", encoding=ENCODING) as heard,
            tempfile.TemporaryFile() as messages,
            subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=messages
            ) as emulator,
        ):
            shell = ShellOperator(emulator, heard, FORBIDDEN)
            try:
                shell.await_line(re.compile(SHELL_READY), BOOT_SECONDS)
                shell.command("mkdir data/soak", COMMAND_SECONDS)
                while time.monotonic() - started < budget_seconds and not shell.violations:
                    sample = run_round(shell, len(samples) + 1, with_network)
                    samples.append(sample)
                    progress(sample)
                shell.send(SHUTDOWN_COMMAND)
                final_lines = shell.drain(SHUTDOWN_SECONDS)
            except (RoundFailedError, GuestSilentError) as error:
                failures.append(str(error))
                emulator.kill()
            failures.extend(f"forbidden line: {line}" for line in shell.violations)
            exit_code = emulator.wait()
            if exit_code != 0 and not failures:
                messages.seek(0)
                detail = messages.read().decode(ENCODING, errors="replace").strip()
                raise InfrastructureError(f"the emulator exited with status {exit_code}: {detail}")
    except OSError as error:
        raise InfrastructureError(f"cannot run the emulator: {error}") from error
    if not failures:
        failures.extend(shutdown_failures(final_lines))
    return SoakSession(
        time.monotonic() - started, tuple(samples), tuple(failures), tuple(final_lines)
    )


def shutdown_failures(final_lines: list[str]) -> list[str]:
    failures = [
        f"the shutdown did not report {pattern!r}"
        for pattern in CLEAN_EXIT
        if not any(re.search(pattern, line) for line in final_lines)
    ]
    if not final_lines or final_lines[-1] != STATUS_PREFIX + KernelStatus.OK:
        failures.append("the kernel did not end with status ok")
    return failures


def analyze(samples: tuple[RoundSample, ...]) -> dict[str, Trend]:
    steady = samples[WARM_UP_ROUNDS:]
    trends = {FREE_FRAMES: decline([sample.counters.get(FREE_FRAMES, 0) for sample in steady])}
    for counter in GROWING_COUNTERS:
        trends[counter] = growth([sample.counters.get(counter, 0) for sample in steady])
    clocks = [sample.guest_clock_us for sample in steady]
    durations = [later - earlier for earlier, later in pairwise(clocks)]
    trends[ROUND_DURATION] = slowdown(durations, TOLERATED_SLOWDOWN)
    return trends


def collector_report(final_lines: tuple[str, ...]) -> dict[str, int]:
    for line in final_lines:
        reported = COLLECTOR.match(line)
        if reported is not None:
            return {name: int(value) for name, value in reported.groupdict().items()}
    return {}


def soak_document(
    session: SoakSession, trends: dict[str, Trend], failures: list[str]
) -> dict[str, object]:
    return {
        "seconds": round(session.seconds, 3),
        "rounds": len(session.samples),
        "warm_up_rounds": WARM_UP_ROUNDS,
        "failures": failures,
        "passed": not failures and len(session.samples) > WARM_UP_ROUNDS,
        "trends": {name: asdict(trend) for name, trend in trends.items()},
        "collector": collector_report(session.final_lines),
        "samples": [
            {"round": sample.number, "guest_clock_us": sample.guest_clock_us, **sample.counters}
            for sample in session.samples
        ],
    }
