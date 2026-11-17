from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class Family(StrEnum):
    BOOT = "boot"
    INTERFACE = "interface"
    STORAGE = "storage"
    NETWORK = "network"


class FailureKind(StrEnum):
    CRASH = "crash"
    HANG = "hang"
    VIOLATION = "violation"


class InvariantError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Failure:
    kind: FailureKind
    signature: str
    detail: str


@dataclass(frozen=True, slots=True)
class Execution:
    failure: Failure | None
    found_coverage: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class InterpretedTarget:
    name: str
    family: Family
    sources: tuple[str, ...]
    max_input_bytes: int
    seeds: Callable[[], tuple[bytes, ...]]
    run: Callable[[bytes], None]
    refusals: tuple[type[Exception], ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class NativeTarget:
    name: str
    family: Family
    sources: tuple[str, ...]
    max_input_bytes: int
    seeds: Callable[[], tuple[bytes, ...]]
    entry: int
    judge: Callable[[bytes, int], None] | None = None


type Target = InterpretedTarget | NativeTarget


@dataclass(frozen=True, slots=True)
class Finding:
    family: Family
    target: str
    failure: Failure
    data: bytes


@dataclass(frozen=True, slots=True)
class TargetRun:
    family: Family
    target: str
    executions: int
    seconds: float
    population: int
    discovered: tuple[bytes, ...]
    findings: tuple[Finding, ...]
