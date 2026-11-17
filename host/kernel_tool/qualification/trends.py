from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import median

MIN_SAMPLES = 4


@dataclass(frozen=True, slots=True)
class Trend:
    samples: int
    earlier_median: float
    later_median: float
    earlier_extreme: int
    later_extreme: int
    persistent: bool


def growth(samples: Sequence[int]) -> Trend:
    return _trend(samples, max, lambda earlier, later: later > earlier)


def decline(samples: Sequence[int]) -> Trend:
    return _trend(samples, min, lambda earlier, later: later < earlier)


def slowdown(durations: Sequence[int], tolerated_factor: float) -> Trend:
    return _trend(durations, max, lambda earlier, later: later > earlier * tolerated_factor)


def _trend(
    samples: Sequence[int],
    extreme: Callable[[Sequence[int]], int],
    worsened: Callable[[float, float], bool],
) -> Trend:
    if len(samples) < MIN_SAMPLES:
        value = samples[-1] if samples else 0
        return Trend(len(samples), value, value, value, value, False)
    middle = len(samples) // 2
    earlier, later = samples[:middle], samples[middle:]
    earlier_median, later_median = median(earlier), median(later)
    earlier_extreme, later_extreme = extreme(earlier), extreme(later)
    persistent = worsened(earlier_median, later_median) and worsened(earlier_extreme, later_extreme)
    return Trend(
        len(samples), earlier_median, later_median, earlier_extreme, later_extreme, persistent
    )
