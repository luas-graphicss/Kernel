from dataclasses import dataclass

from kernel_tool.faults.crash_images import crash_image, losses, split
from kernel_tool.faults.device_log import DeviceEvent, describe, published_generation
from kernel_tool.faults.recovery import History, RecordedVolume, recover
from kernel_tool.faults.transactions import TRANSACTIONS, Transaction, baseline

BEFORE_ANY_EVENT = "nothing"


@dataclass(frozen=True, slots=True)
class CrashPoint:
    transaction: str
    executed: int
    after: str
    images: int
    recovered_before: int
    recovered_after: int
    failures: tuple[str, ...]


def run_matrix() -> list[CrashPoint]:
    base = baseline()
    points = []
    for name, transaction in TRANSACTIONS:
        points.extend(transaction_points(name, transaction, base))
    return points


def transaction_points(name: str, transaction: Transaction, base: bytes) -> list[CrashPoint]:
    recorded = RecordedVolume(base)
    transaction(recorded.volume)
    recorded.volume.sync()
    events = recorded.store.events
    published = _publish_index(events)
    return [
        _crash_point(name, base, events, recorded.history, executed, published)
        for executed in range(len(events) + 1)
    ]


def _publish_index(events: list[DeviceEvent]) -> int:
    for index, event in enumerate(events):
        if published_generation(event) is not None:
            return index
    return len(events)


def _crash_point(
    name: str,
    base: bytes,
    events: list[DeviceEvent],
    history: History,
    executed: int,
    published: int,
) -> CrashPoint:
    before = history.commits[0].generation
    durable, volatile = split(events, executed)
    patterns = losses(len(volatile))
    failures = []
    recovered_before = 0
    for loss in patterns:
        recovery = recover(crash_image(base, durable, volatile, loss), history, executed)
        if recovery.failure is not None:
            failures.append(f"{loss.describe()}: {recovery.failure}")
        elif recovery.generation == before:
            recovered_before += 1
        elif executed <= published:
            failures.append(f"{loss.describe()}: the change shows before its superblock was sent")
    return CrashPoint(
        transaction=name,
        executed=executed,
        after=describe(events[executed - 1]) if executed else BEFORE_ANY_EVENT,
        images=len(patterns),
        recovered_before=recovered_before,
        recovered_after=len(patterns) - recovered_before - len(failures),
        failures=tuple(failures),
    )
