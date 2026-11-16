import random
from dataclasses import dataclass

MILLISECOND = 0.001


@dataclass(frozen=True, slots=True)
class Fate:
    delays: tuple[float, ...]

    @property
    def is_lost(self) -> bool:
        return not self.delays


class Impairment:
    def __init__(self, policy: dict[str, float], seed: int) -> None:
        self._loss = float(policy.get("loss", 0.0))
        self._duplicate = float(policy.get("duplicate", 0.0))
        self._reorder = float(policy.get("reorder", 0.0))
        self._reorder_seconds = float(policy.get("reorder_milliseconds", 0)) * MILLISECOND
        self._delay_seconds = float(policy.get("delay_milliseconds", 0)) * MILLISECOND
        self._random = random.Random(seed)

    def decide(self) -> Fate:
        if self._random.random() < self._loss:
            return Fate(())
        delay = self._delay_seconds
        if self._random.random() < self._reorder:
            delay += self._random.random() * self._reorder_seconds
        if self._random.random() < self._duplicate:
            return Fate((delay, delay + self._random.random() * self._reorder_seconds))
        return Fate((delay,))
