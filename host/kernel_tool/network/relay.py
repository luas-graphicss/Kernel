import heapq
import os
import select
import socket
import time
from collections.abc import Callable
from pathlib import Path

from kernel_tool.network.capture import Capture
from kernel_tool.network.impairment import Impairment

FRAME_BYTES = 65536
IDLE_SECONDS = 0.2
TO_GUEST = 0
TO_PEER = 1


class Relay:
    def __init__(
        self,
        tap: int,
        wire: socket.socket,
        guest: Path,
        uplink: Impairment,
        downlink: Impairment,
        capture: Capture,
    ) -> None:
        self._tap = tap
        self._wire = wire
        self._guest = str(guest)
        self._uplink = uplink
        self._downlink = downlink
        self._capture = capture
        self._pending: list[tuple[float, int, int, bytes]] = []
        self._order = 0
        self._dark_until = 0.0
        self.carried = [0, 0]
        self.lost = [0, 0]
        self.injected = 0

    def darken(self, seconds: float) -> None:
        self._dark_until = time.monotonic() + seconds

    def inject(self, frame: bytes) -> None:
        self.injected += 1
        self._deliver(TO_GUEST, frame)

    def run(self, control: int, on_control: Callable[[], bool]) -> None:
        wire = self._wire.fileno()
        running = True
        while running:
            timeout = IDLE_SECONDS
            if self._pending:
                timeout = min(timeout, max(self._pending[0][0] - time.monotonic(), 0.0))
            readable, _writable, _failed = select.select(
                [self._tap, wire, control], [], [], timeout
            )
            if wire in readable:
                self._schedule(TO_PEER, self._wire.recv(FRAME_BYTES), self._uplink)
            if self._tap in readable:
                self._schedule(TO_GUEST, os.read(self._tap, FRAME_BYTES), self._downlink)
            if control in readable:
                running = on_control()
            self._release_due()

    def _schedule(self, direction: int, frame: bytes, impairment: Impairment) -> None:
        if direction == TO_PEER:
            self._capture.record(frame)
        fate = impairment.decide()
        if fate.is_lost or time.monotonic() < self._dark_until:
            self.lost[direction] += 1
            return
        for delay in fate.delays:
            self._order += 1
            heapq.heappush(self._pending, (time.monotonic() + delay, self._order, direction, frame))

    def _release_due(self) -> None:
        now = time.monotonic()
        while self._pending and self._pending[0][0] <= now:
            _due, _order, direction, frame = heapq.heappop(self._pending)
            self._deliver(direction, frame)

    def _deliver(self, direction: int, frame: bytes) -> None:
        self.carried[direction] += 1
        try:
            if direction == TO_PEER:
                os.write(self._tap, frame)
            else:
                self._capture.record(frame)
                self._wire.sendto(frame, self._guest)
        except OSError:
            self.lost[direction] += 1
