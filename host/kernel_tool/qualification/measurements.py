import re

from kernel_tool.outcome import CheckError
from kernel_tool.qualification.budgets import (
    COLLECTOR_LONGEST_PAUSE,
    COLLECTOR_PAUSE,
    IDLE_MEMORY,
    LOADED_MEMORY,
)

MEASURE = re.compile(
    r"measure: name=(?P<name>\S+) samples=(?P<samples>\d+) "
    r"p50-us=(?P<p50>\d+) p99-us=(?P<p99>\d+) max-us=(?P<max>\d+)$"
)
MEMORY = re.compile(r"mem: frames-usable=\d+ frames-free=\d+ frames-reserved=\d+ bytes-free=(\d+)$")
COLLECTOR = re.compile(
    r"^policy: collector=measured collections=(?P<collections>\d+) pause-total-us=(?P<total>\d+) "
    r"pause-p99-us=(?P<p99>\d+) pause-longest-us=(?P<longest>\d+)$"
)
MEMORY_REPORTS = 2
COLLECTIONS = "collector-collections"


def guest_measurements(lines: tuple[str, ...]) -> dict[str, float]:
    measured: dict[str, float] = {}
    for line in lines:
        match = MEASURE.search(line)
        if match is not None:
            name = match["name"]
            measured[f"{name}-samples"] = int(match["samples"])
            measured[f"{name}-p50-us"] = int(match["p50"])
            measured[f"{name}-p99-us"] = int(match["p99"])
            measured[f"{name}-max-us"] = int(match["max"])
    return measured


def memory_measurements(lines: tuple[str, ...], memory_bytes: int) -> dict[str, float]:
    free = [int(match[1]) for line in lines if (match := MEMORY.search(line)) is not None]
    if len(free) != MEMORY_REPORTS:
        raise CheckError(
            f"the guest reported its memory {len(free)} times instead of {MEMORY_REPORTS}"
        )
    idle, loaded = free
    return {IDLE_MEMORY: memory_bytes - idle, LOADED_MEMORY: memory_bytes - loaded}


def collector_measurements(sessions: tuple[tuple[str, ...], ...]) -> dict[str, float]:
    reports = [
        match
        for lines in sessions
        for line in lines
        if (match := COLLECTOR.match(line)) is not None
    ]
    if len(reports) != len(sessions):
        raise CheckError("a measured session did not report the supervisor collector")
    collections = sum(int(report["collections"]) for report in reports)
    measured: dict[str, float] = {COLLECTIONS: collections}
    if collections:
        measured[COLLECTOR_PAUSE] = max(int(report["p99"]) for report in reports)
        measured[COLLECTOR_LONGEST_PAUSE] = max(int(report["longest"]) for report in reports)
    return measured
