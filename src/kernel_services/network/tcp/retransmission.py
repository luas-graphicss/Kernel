INITIAL_TIMEOUT_NANOSECONDS = 1000000000
MINIMUM_TIMEOUT_NANOSECONDS = 200000000
MAXIMUM_TIMEOUT_NANOSECONDS = 60000000000
CLOCK_GRANULARITY_NANOSECONDS = 10000000


class RoundTripEstimator:
    def __init__(self) -> None:
        self.timeout = INITIAL_TIMEOUT_NANOSECONDS
        self._smoothed = 0
        self._variation = 0
        self._has_sample = False

    def sample(self, round_trip_nanoseconds: int) -> None:
        if not self._has_sample:
            self._smoothed = round_trip_nanoseconds
            self._variation = round_trip_nanoseconds // 2
            self._has_sample = True
        else:
            error = self._smoothed - round_trip_nanoseconds
            if error < 0:
                error = -error
            self._variation = (3 * self._variation + error) // 4
            self._smoothed = (7 * self._smoothed + round_trip_nanoseconds) // 8
        margin = 4 * self._variation
        if margin < CLOCK_GRANULARITY_NANOSECONDS:
            margin = CLOCK_GRANULARITY_NANOSECONDS
        self.timeout = bounded(self._smoothed + margin)

    def back_off(self) -> None:
        self.timeout = bounded(self.timeout * 2)


def bounded(timeout: int) -> int:
    if timeout < MINIMUM_TIMEOUT_NANOSECONDS:
        return MINIMUM_TIMEOUT_NANOSECONDS
    if timeout > MAXIMUM_TIMEOUT_NANOSECONDS:
        return MAXIMUM_TIMEOUT_NANOSECONDS
    return timeout
