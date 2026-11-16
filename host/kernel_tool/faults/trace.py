from collections.abc import Sequence
from dataclasses import dataclass

from kernel_services.filesystem.recovery.digest import tree_digest
from kernel_services.filesystem.volume import Volume
from kernel_tool.faults.crash_images import crash_image, losses, split
from kernel_tool.faults.device_log import DeviceEvent, DeviceFlush, describe, published_generation
from kernel_tool.faults.recovery import History, recover
from kernel_tool.storage.image_store import ImageStore

EVENTS_UNTIL_CONFIRMED = 2
HEXADECIMAL = 16


@dataclass(frozen=True, slots=True)
class TraceResult:
    events: tuple[str, ...]
    generations: tuple[int, ...]
    images: int
    failures: tuple[str, ...]


def check_trace(
    base: bytes, events: Sequence[DeviceEvent], reported: Sequence[tuple[int, str]]
) -> TraceResult:
    volume = Volume(ImageStore(base))
    history = History(volume.generation(), tree_digest(volume))
    digests = {generation: int(digest, HEXADECIMAL) for generation, digest in reported}
    failures: list[str] = []
    published = []
    for index, event in enumerate(events):
        generation = published_generation(event)
        if generation is None:
            continue
        published.append(generation)
        failures.extend(_barrier_failures(events, index, generation))
        if generation in digests:
            history.record(generation, digests[generation], index + EVENTS_UNTIL_CONFIRMED)
        else:
            failures.append(f"generation {generation} reached the device without a report")
    failures.extend(
        f"generation {generation} was reported but its superblock never reached the device"
        for generation in sorted(set(digests) - set(published))
    )
    images = 0
    for executed in range(len(events) + 1):
        durable, volatile = split(events, executed)
        for loss in losses(len(volatile)):
            images += 1
            recovery = recover(crash_image(base, durable, volatile, loss), history, executed)
            if recovery.failure is not None:
                failures.append(
                    f"after {executed} events with {loss.describe()}: {recovery.failure}"
                )
    return TraceResult(
        events=tuple(describe(event) for event in events),
        generations=tuple(published),
        images=images,
        failures=tuple(failures),
    )


def _barrier_failures(events: Sequence[DeviceEvent], index: int, generation: int) -> list[str]:
    failures = []
    if index == 0 or not isinstance(events[index - 1], DeviceFlush):
        failures.append(
            f"the superblock of generation {generation} left before its tree was flushed"
        )
    if index + 1 >= len(events) or not isinstance(events[index + 1], DeviceFlush):
        failures.append(f"the superblock of generation {generation} was not flushed at once")
    return failures
