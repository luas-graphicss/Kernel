UNLIMITED_THRESHOLD = 1 << 30
DUPLICATES_FOR_RETRANSMISSION = 3
LARGE_SEGMENT_BYTES = 2190
MEDIUM_SEGMENT_BYTES = 1095


def initial_window(segment_bytes: int) -> int:
    if segment_bytes > LARGE_SEGMENT_BYTES:
        return 2 * segment_bytes
    if segment_bytes > MEDIUM_SEGMENT_BYTES:
        return 3 * segment_bytes
    return 4 * segment_bytes


class CongestionControl:
    def __init__(self, segment_bytes: int) -> None:
        self.segment_bytes = segment_bytes
        self.window = initial_window(segment_bytes)
        self.threshold = UNLIMITED_THRESHOLD
        self.duplicates = 0
        self.is_recovering = False
        self.recovery_point = 0

    def use_segment_bytes(self, segment_bytes: int) -> None:
        self.segment_bytes = segment_bytes
        self.window = initial_window(segment_bytes)

    def acknowledged(self, acknowledged_bytes: int) -> None:
        self.duplicates = 0
        if self.window < self.threshold:
            growth = acknowledged_bytes
            if growth > self.segment_bytes:
                growth = self.segment_bytes
        else:
            growth = self.segment_bytes * self.segment_bytes // self.window
            if growth == 0:
                growth = 1
        self.window += growth

    def duplicate_acknowledgment(self) -> bool:
        self.duplicates += 1
        if self.is_recovering:
            self.window += self.segment_bytes
            return False
        return self.duplicates == DUPLICATES_FOR_RETRANSMISSION

    def enter_recovery(self, flight_bytes: int, recovery_point: int) -> None:
        self.threshold = self._reduced(flight_bytes)
        self.window = self.threshold + DUPLICATES_FOR_RETRANSMISSION * self.segment_bytes
        self.is_recovering = True
        self.recovery_point = recovery_point

    def partially_acknowledged(self, acknowledged_bytes: int) -> None:
        self.window -= acknowledged_bytes
        if self.window < 0:
            self.window = 0
        self.window += self.segment_bytes

    def leave_recovery(self) -> None:
        self.window = self.threshold
        self.is_recovering = False
        self.duplicates = 0

    def timed_out(self, flight_bytes: int) -> None:
        self.threshold = self._reduced(flight_bytes)
        self.window = self.segment_bytes
        self.is_recovering = False
        self.duplicates = 0

    def _reduced(self, flight_bytes: int) -> int:
        reduced = flight_bytes // 2
        if reduced < 2 * self.segment_bytes:
            return 2 * self.segment_bytes
        return reduced
