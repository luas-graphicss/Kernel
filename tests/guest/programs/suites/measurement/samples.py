NANOSECONDS_PER_MICROSECOND = 1000
PERCENT = 100
MEDIAN = 50
TAIL = 99


def percentile(ordered: list[int], percent: int) -> int:
    position = (len(ordered) * percent + PERCENT - 1) // PERCENT
    if position < 1:
        position = 1
    return ordered[position - 1]


def report(name: str, durations: list[int]) -> None:
    ordered = sorted(durations)
    print(
        f"measure: name={name} samples={len(ordered)} "
        f"p50-us={percentile(ordered, MEDIAN) // NANOSECONDS_PER_MICROSECOND} "
        f"p99-us={percentile(ordered, TAIL) // NANOSECONDS_PER_MICROSECOND} "
        f"max-us={ordered[-1] // NANOSECONDS_PER_MICROSECOND}"
    )
