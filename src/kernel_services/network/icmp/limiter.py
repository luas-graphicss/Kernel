class RateLimiter:
    def __init__(self, burst: int, interval_nanoseconds: int) -> None:
        self._burst = burst
        self._interval = interval_nanoseconds
        self._tokens = burst
        self._refilled_at = 0

    def allow(self, now: int) -> bool:
        earned = (now - self._refilled_at) // self._interval
        if earned > 0:
            self._refilled_at += earned * self._interval
            self._tokens += earned
            if self._tokens > self._burst:
                self._tokens = self._burst
        if self._tokens == 0:
            return False
        self._tokens -= 1
        return True
