class Resolution:
    def __init__(self, retry_at: int) -> None:
        self.attempts = 1
        self.retry_at = retry_at
        self.datagrams: list[bytes] = []


class PendingResolutions:
    def __init__(
        self, max_targets: int, max_datagrams: int, max_attempts: int, retry_nanoseconds: int
    ) -> None:
        self._max_targets = max_targets
        self._max_datagrams = max_datagrams
        self._max_attempts = max_attempts
        self._retry = retry_nanoseconds
        self._targets: dict[int, Resolution] = {}

    def is_pending(self, target: int) -> bool:
        return target in self._targets

    def has_room(self, target: int) -> bool:
        resolution = self._targets.get(target)
        if resolution is None:
            return len(self._targets) < self._max_targets
        return len(resolution.datagrams) < self._max_datagrams

    def hold(self, target: int, datagram: bytes, now: int) -> bool:
        is_new = target not in self._targets
        if is_new:
            self._targets[target] = Resolution(now + self._retry)
        self._targets[target].datagrams.append(datagram)
        return is_new

    def release(self, target: int) -> list[bytes]:
        resolution = self._targets.pop(target, None)
        if resolution is None:
            return []
        return resolution.datagrams

    def due(self, now: int) -> tuple[list[int], list[int]]:
        retried = []
        abandoned = []
        for target in sorted(self._targets):
            resolution = self._targets[target]
            if resolution.retry_at > now:
                continue
            if resolution.attempts == self._max_attempts:
                abandoned.append(target)
                continue
            resolution.attempts += 1
            resolution.retry_at = now + self._retry
            retried.append(target)
        for target in abandoned:
            del self._targets[target]
        return retried, abandoned

    def next_deadline(self, none: int) -> int:
        deadline = none
        for target in self._targets:
            if self._targets[target].retry_at < deadline:
                deadline = self._targets[target].retry_at
        return deadline

    def clear(self) -> None:
        self._targets = {}
