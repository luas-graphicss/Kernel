from dataclasses import dataclass

MIB = 1 << 20
MICROSECONDS_PER_MILLISECOND = 1000
MICROSECONDS_PER_SECOND = 1000000
BOOT_TO_SHELL = "boot-to-shell-seconds"
IDLE_MEMORY = "idle-committed-bytes"
LOADED_MEMORY = "loaded-committed-bytes"
IPC_ROUND_TRIP = "ipc-round-trip-p99-us"
READY_TASK_RESPONSE = "ready-task-response-p99-us"
COLLECTOR_PAUSE = "collector-pause-p99-us"
COLLECTOR_LONGEST_PAUSE = "collector-pause-longest-us"
RELEASE_AFTER_EXIT = "release-after-exit-max-us"


@dataclass(frozen=True, slots=True)
class Budget:
    metric: str
    limit: float
    condition: str


@dataclass(frozen=True, slots=True)
class Verdict:
    metric: str
    limit: float
    value: float | None
    met: bool
    condition: str


BUDGETS = (
    Budget(
        BOOT_TO_SHELL,
        15,
        "host clock from the start of the emulator until the ordered shutdown ends, "
        "release image, valid volume and isolated network",
    ),
    Budget(
        IDLE_MEMORY,
        96 * MIB,
        "machine memory minus free frames with the mandatory services and the shell idle",
    ),
    Budget(
        LOADED_MEMORY,
        224 * MIB,
        "machine memory minus free frames with every application slot holding its heap",
    ),
    Budget(
        IPC_ROUND_TRIP,
        25 * MICROSECONDS_PER_MILLISECOND,
        "guest clock, 10000 calls to an echo process, no disk and no network",
    ),
    Budget(
        READY_TASK_RESPONSE,
        250 * MICROSECONDS_PER_MILLISECOND,
        "guest clock, delay after a timer deadline with the mandatory services, "
        "four processor-bound applications and two file-bound applications",
    ),
    Budget(
        COLLECTOR_PAUSE,
        25 * MICROSECONDS_PER_MILLISECOND,
        "supervisor collector pauses of the loaded system session, 99th percentile",
    ),
    Budget(
        COLLECTOR_LONGEST_PAUSE,
        100 * MICROSECONDS_PER_MILLISECOND,
        "longest supervisor collector pause observed in the loaded system session",
    ),
    Budget(
        RELEASE_AFTER_EXIT,
        MICROSECONDS_PER_SECOND,
        "guest clock from the kill of a process until every frame it held is free again",
    ),
)


def judge(measured: dict[str, float], budgets: tuple[Budget, ...] = BUDGETS) -> list[Verdict]:
    verdicts = []
    for budget in budgets:
        value = measured.get(budget.metric)
        met = value is not None and value <= budget.limit
        verdicts.append(Verdict(budget.metric, budget.limit, value, met, budget.condition))
    return verdicts
