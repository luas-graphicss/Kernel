import itertools
import random
from collections.abc import Sequence
from dataclasses import dataclass

from kernel_services.filesystem.format.layout import BLOCK_BYTES
from kernel_tool.faults.device_log import DeviceEvent, DeviceFlush, DeviceWrite

TORN_BYTES = BLOCK_BYTES // 2
EXHAUSTIVE_WRITES = 4
TORN_ONE_IN = 4


@dataclass(frozen=True, slots=True)
class Loss:
    kept: frozenset[int]
    torn: int | None = None

    def describe(self) -> str:
        kept = ",".join(str(index) for index in sorted(self.kept)) or "none"
        return f"kept={kept}" if self.torn is None else f"kept={kept} torn={self.torn}"


def split(
    events: Sequence[DeviceEvent], executed: int
) -> tuple[list[DeviceWrite], list[DeviceWrite]]:
    durable: list[DeviceWrite] = []
    volatile: list[DeviceWrite] = []
    for event in events[:executed]:
        if isinstance(event, DeviceFlush):
            durable.extend(volatile)
            volatile = []
        else:
            volatile.append(event)
    return durable, volatile


def losses(volatile: int) -> list[Loss]:
    everything = range(volatile)
    if volatile <= EXHAUSTIVE_WRITES:
        kept_sets = [
            frozenset(kept)
            for size in range(volatile + 1)
            for kept in itertools.combinations(everything, size)
        ]
    else:
        kept_sets = [frozenset(range(size)) for size in range(volatile + 1)]
        kept_sets.extend(frozenset((index,)) for index in everything)
        kept_sets.extend(frozenset(everything) - {index} for index in everything)
    found = [Loss(kept) for kept in kept_sets]
    for index in everything:
        found.append(Loss(frozenset(range(index)), index))
        found.append(Loss(frozenset(everything) - {index}, index))
    return list(dict.fromkeys(found))


def random_loss(volatile: int, generator: random.Random) -> Loss:
    kept = frozenset(index for index in range(volatile) if generator.random() < 0.5)
    if volatile == 0 or generator.randrange(TORN_ONE_IN) != 0:
        return Loss(kept)
    return Loss(kept, generator.randrange(volatile))


def crash_image(
    base: bytes, durable: Sequence[DeviceWrite], volatile: Sequence[DeviceWrite], loss: Loss
) -> bytes:
    image = bytearray(base)
    for write in durable:
        _store(image, write.block, write.data)
    for index, write in enumerate(volatile):
        if index == loss.torn:
            start = write.block * BLOCK_BYTES
            image[start : start + TORN_BYTES] = write.data[:TORN_BYTES]
        elif index in loss.kept:
            _store(image, write.block, write.data)
    return bytes(image)


def _store(image: bytearray, block: int, data: bytes) -> None:
    image[block * BLOCK_BYTES : (block + 1) * BLOCK_BYTES] = data
