from kernel_drivers.virtio_network.driver import NetworkDriver

POLL = 0
RECEIVE_BATCH = 8
BACKLOG_FRAMES = 64
RECOVERY_ATTEMPTS = 3
RECOVERY_INTERVAL_NANOSECONDS = 1000000000


class Link:
    def __init__(self, driver: NetworkDriver) -> None:
        self._driver = driver
        self._backlog: list[bytes] = []
        self._recoveries = 0
        self._recover_at = 0
        self.dropped_frames = 0

    def hardware(self) -> bytes:
        return self._driver.hardware

    def resets(self) -> int:
        return self._driver.resets

    def is_linked(self) -> bool:
        return self._driver.is_linked()

    def receive(self, deadline: int) -> list[bytes]:
        frames = []
        event = self._driver.wait(deadline)
        while event is not None:
            if event:
                frames.append(event)
            if len(frames) == RECEIVE_BATCH:
                break
            event = self._driver.wait(POLL)
        self._flush()
        return frames

    def transmit(self, frames: list[bytes]) -> None:
        for frame in frames:
            if len(self._backlog) == BACKLOG_FRAMES:
                self.dropped_frames += 1
            else:
                self._backlog.append(frame)
        self._flush()

    def recover(self, now: int) -> bool:
        if not self._driver.has_failed:
            return False
        if self._recoveries == RECOVERY_ATTEMPTS or now < self._recover_at:
            return False
        self._recoveries += 1
        self._recover_at = now + RECOVERY_INTERVAL_NANOSECONDS
        self.dropped_frames += len(self._backlog)
        self._backlog = []
        if not self._driver.recover():
            return False
        self._recoveries = 0
        return True

    def has_failed(self) -> bool:
        return self._driver.has_failed

    def close(self) -> None:
        self._driver.close()

    def _flush(self) -> None:
        while self._backlog and self._driver.can_transmit():
            if not self._driver.transmit(self._backlog[0]):
                return
            self._backlog.pop(0)
