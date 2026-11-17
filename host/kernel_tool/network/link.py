import json
import os
import queue
import subprocess
import sys
import threading
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType

from kernel_tool.network.plan import GUEST_HARDWARE, NetworkPlan
from kernel_tool.network.sockets import GUEST_SOCKET, STATION_SOCKET, socket_directory
from kernel_tool.network.station import CAPTURE_FILE
from kernel_tool.outcome import InfrastructureError

HOST_PACKAGES = Path(__file__).resolve().parents[2]
PLAN_FILE = "plan.json"
MODULE = "kernel_tool.network.station"
READY_TIMEOUT_SECONDS = 30.0
STOP_TIMEOUT_SECONDS = 10.0
PROBE_TIMEOUT_SECONDS = 30.0
NETWORK_DEVICE = "net0"
UNAVAILABLE = (
    "the network suites need an isolated network: run as root, allow user namespaces "
    "with access to /dev/net/tun, or allow sudo without a password"
)


def station_command(arguments: list[str]) -> list[str]:
    return [sys.executable, "-m", MODULE, *arguments]


def station_environment() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(HOST_PACKAGES), "PYTHONUNBUFFERED": "1"}


def privileged(command: list[str]) -> list[str]:
    return ["sudo", "-n", "env", f"PYTHONPATH={HOST_PACKAGES}", "PYTHONUNBUFFERED=1", *command]


def _succeeds(command: list[str]) -> bool:
    try:
        completed = subprocess.run(
            command,
            env=station_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def isolated_command(arguments: list[str]) -> list[str]:
    command = station_command(arguments)
    if os.geteuid() == 0:
        return command
    if _succeeds([*command, "--rootless", "--probe"]):
        return [*command, "--rootless"]
    if _succeeds(["sudo", "-n", "true"]):
        return privileged(command)
    raise InfrastructureError(UNAVAILABLE)


class StationLink:
    def __init__(self, directory: Path, plan: NetworkPlan) -> None:
        self._directory = directory
        self._plan = plan
        self._sockets = socket_directory()
        self._process: subprocess.Popen[str] | None = None
        self._heard: queue.Queue[dict[str, object]] = queue.Queue()
        self._events: list[dict[str, object]] = []
        self._reader: threading.Thread | None = None
        self.stack = ""

    def __enter__(self) -> "StationLink":
        directory = self._directory
        directory.mkdir(parents=True, exist_ok=True)
        (directory / CAPTURE_FILE).unlink(missing_ok=True)
        plan = directory / PLAN_FILE
        plan.write_text(json.dumps(self._plan.to_document(), sort_keys=True), encoding="utf-8")
        with ExitStack() as failure:
            failure.callback(self.stop)
            self._start(
                [
                    "--directory",
                    str(directory),
                    "--sockets",
                    self._sockets.name,
                    "--plan",
                    str(plan),
                ]
            )
            failure.pop_all()
        return self

    def _start(self, arguments: list[str]) -> None:
        command = isolated_command(arguments)
        try:
            self._process = subprocess.Popen(
                command,
                env=station_environment(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as error:
            raise InfrastructureError(f"cannot start the network station: {error}") from error
        self._reader = threading.Thread(target=self._listen, daemon=True)
        self._reader.start()
        self._await_ready()

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.stop()

    @property
    def capture(self) -> Path:
        return self._directory / CAPTURE_FILE

    def emulator_arguments(self) -> list[str]:
        guest = Path(self._sockets.name) / GUEST_SOCKET
        station = Path(self._sockets.name) / STATION_SOCKET
        guest.unlink(missing_ok=True)
        return [
            "-netdev",
            f"dgram,id={NETWORK_DEVICE},local.type=unix,local.path={guest},"
            f"remote.type=unix,remote.path={station}",
            "-device",
            f"virtio-net-device,netdev={NETWORK_DEVICE},mac={GUEST_HARDWARE}",
        ]

    def send(self, command: dict[str, object]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            return
        try:
            process.stdin.write(json.dumps(command, sort_keys=True) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, ValueError):
            return

    def events(self) -> tuple[dict[str, object], ...]:
        while True:
            try:
                self._events.append(self._heard.get_nowait())
            except queue.Empty:
                return tuple(self._events)

    def stop(self) -> None:
        self._stop_station()
        self._sockets.cleanup()

    def _stop_station(self) -> None:
        process = self._process
        if process is None:
            return
        self.send({"command": "stop"})
        self._process = None
        try:
            if process.stdin is not None:
                process.stdin.close()
        except (BrokenPipeError, ValueError):
            pass
        try:
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if self._reader is not None:
            self._reader.join(timeout=STOP_TIMEOUT_SECONDS)

    def _listen(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                self._heard.put(event)

    def _await_ready(self) -> None:
        try:
            event = self._heard.get(timeout=READY_TIMEOUT_SECONDS)
        except queue.Empty:
            event = {}
        if event.get("event") != "ready":
            detail = self._failure()
            self.stop()
            raise InfrastructureError(f"the network station did not start: {detail}")
        self._events.append(event)
        self.stack = str(event.get("stack", ""))

    def _failure(self) -> str:
        process = self._process
        if process is None or process.stderr is None:
            return "no diagnostics"
        if process.poll() is None:
            process.kill()
            process.wait()
        return process.stderr.read().strip()[-400:] or "no diagnostics"
