import argparse
import json
import os
import platform
import socket
import sys
import threading
from pathlib import Path

from kernel_tool.network.capture import Capture
from kernel_tool.network.impairment import Impairment
from kernel_tool.network.isolation import build_interface
from kernel_tool.network.peers import Peers
from kernel_tool.network.relay import Relay
from kernel_tool.network.sockets import GUEST_SOCKET, STATION_SOCKET

INTERFACE = "tap0"
CAPTURE_FILE = "traffic.pcap"
SNAP_BYTES = 96
SOCKET_MODE = 0o666
CAPTURE_MODE = 0o644
MILLISECOND = 0.001
UPLINK_SEED_OFFSET = 0
DOWNLINK_SEED_OFFSET = 1


class Station:
    def __init__(
        self, directory: Path, sockets: Path, plan: dict[str, object], rootless: bool
    ) -> None:
        self._directory = directory
        self._lock = threading.Lock()
        self._input = b""
        tap = build_interface(INTERFACE, str(plan["address"]), int(str(plan["prefix"])), rootless)
        wire = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        wire.bind(str(sockets / STATION_SOCKET))
        Path(sockets / STATION_SOCKET).chmod(SOCKET_MODE)
        self._capture = Capture(directory / CAPTURE_FILE, SNAP_BYTES)
        Path(directory / CAPTURE_FILE).chmod(CAPTURE_MODE)
        seed = int(str(plan["seed"]))
        self._relay = Relay(
            tap,
            wire,
            sockets / GUEST_SOCKET,
            Impairment(_policy(plan, "uplink"), seed + UPLINK_SEED_OFFSET),
            Impairment(_policy(plan, "downlink"), seed + DOWNLINK_SEED_OFFSET),
            self._capture,
        )
        self._peers = Peers(str(plan["address"]), str(plan["guest"]), self.report)

    def report(self, event: dict[str, object]) -> None:
        with self._lock:
            sys.stdout.write(json.dumps(event, sort_keys=True) + "\n")
            sys.stdout.flush()

    def run(self) -> None:
        self._peers.start()
        self.report({"event": "ready", "stack": f"{platform.system()} {platform.release()}"})
        self._relay.run(sys.stdin.fileno(), self._read_commands)
        self._peers.stop()
        self._capture.close()
        self.report(
            {
                "event": "stopped",
                "to-guest": self._relay.carried[0],
                "to-peer": self._relay.carried[1],
                "lost-to-guest": self._relay.lost[0],
                "lost-to-peer": self._relay.lost[1],
                "injected": self._relay.injected,
                "captured": self._capture.frames,
            }
        )

    def _read_commands(self) -> bool:
        chunk = os.read(sys.stdin.fileno(), 65536)
        if not chunk:
            return False
        self._input += chunk
        while b"\n" in self._input:
            line, _separator, self._input = self._input.partition(b"\n")
            if line.strip() and not self._obey(json.loads(line)):
                return False
        return True

    def _obey(self, command: dict[str, object]) -> bool:
        name = command.get("command")
        if name == "stop":
            return False
        if name == "call":
            self._peers.call(
                int(str(command["port"])), int(str(command["seed"])), int(str(command["bytes"]))
            )
        elif name == "inject":
            frames = command["frames"]
            if isinstance(frames, list):
                for frame in frames:
                    self._relay.inject(bytes.fromhex(str(frame)))
        elif name == "darken":
            self._relay.darken(float(str(command["milliseconds"])) * MILLISECOND)
        self.report({"event": "obeyed", "command": str(name)})
        return True


def _policy(document: dict[str, object], name: str) -> dict[str, float]:
    policy = document.get(name, {})
    if not isinstance(policy, dict):
        return {}
    return {str(key): float(value) for key, value in policy.items()}


def main() -> int:
    parser = argparse.ArgumentParser(prog="kernel-tool-network-station")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--sockets", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--rootless", action="store_true")
    parser.add_argument("--probe", action="store_true")
    options = parser.parse_args()
    plan = json.loads(options.plan.read_text(encoding="utf-8"))
    if options.probe:
        build_interface(INTERFACE, str(plan["address"]), int(str(plan["prefix"])), options.rootless)
        return 0
    Station(options.directory, options.sockets, plan, options.rootless).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
