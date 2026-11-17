import random
from collections.abc import Callable
from pathlib import Path

from kernel_tool.fuzzing.engine import fuzz, replay
from kernel_tool.fuzzing.interpreted import InterpretedExecutor
from kernel_tool.fuzzing.minimization import minimize
from kernel_tool.fuzzing.model import (
    Execution,
    Failure,
    FailureKind,
    Family,
    InterpretedTarget,
    InvariantError,
)
from kernel_tool.fuzzing.mutation import Mutator

MAX_BYTES = 48
MARKER = 0xFF
BUDGET_TICKS = 4000.0
TIME_LIMIT_SECONDS = 0.2
SOURCES = Path(__file__).parent


class RefusedInputError(Exception):
    pass


class Ticks:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


class MarkerExecutor:
    def __init__(self) -> None:
        self.seen: set[int] = set()

    def execute(self, data: bytes) -> Execution:
        if MARKER in data:
            return Execution(Failure(FailureKind.CRASH, "marker reached", "detail"), False)
        fresh = set(data) - self.seen
        self.seen |= fresh
        return Execution(None, bool(fresh))


def judged(data: bytes) -> None:
    if data.startswith(b"refuse"):
        raise RefusedInputError
    if data.startswith(b"violate"):
        raise InvariantError("the invariant does not hold")
    if data.startswith(b"crash"):
        raise ValueError("unexpected")
    while data.startswith(b"hang"):
        pass


def target(run: Callable[[bytes], None] = judged) -> InterpretedTarget:
    return InterpretedTarget(
        name="planted",
        family=Family.BOOT,
        sources=(),
        max_input_bytes=MAX_BYTES,
        seeds=lambda: (b"seed",),
        run=run,
        refusals=(RefusedInputError,),
    )


def test_the_same_seed_produces_the_same_mutations_within_the_size_limit() -> None:
    first = Mutator(random.Random(7), MAX_BYTES)
    second = Mutator(random.Random(7), MAX_BYTES)

    produced = [first.mutate(b"parent input", b"donor") for _ in range(200)]

    assert produced == [second.mutate(b"parent input", b"donor") for _ in range(200)]
    assert all(len(candidate) <= MAX_BYTES for candidate in produced)
    assert len(set(produced)) > 100


def test_minimization_keeps_what_makes_the_input_fail() -> None:
    smallest = minimize(b"padding BOOM padding", lambda candidate: b"BOOM" in candidate, 96)

    assert b"BOOM" in smallest
    assert len(smallest) < len(b"padding BOOM padding")


def test_replay_separates_the_inputs_that_fail() -> None:
    accepted, findings = replay(target(), MarkerExecutor(), (b"good", bytes([MARKER]), b"good"))

    assert accepted == [b"good"]
    assert [finding.data for finding in findings] == [bytes([MARKER])]


def test_fuzzing_reports_a_failure_once_with_a_reduced_input() -> None:
    run = fuzz(target(), MarkerExecutor(), (b"seed",), BUDGET_TICKS, 1, Ticks())

    assert [finding.failure.signature for finding in run.findings] == ["marker reached"]
    assert run.findings[0].data == bytes([MARKER])
    assert run.executions > len(run.discovered) > 0
    assert run.population == len(run.discovered) + 1


def test_refusals_are_expected_and_other_exceptions_are_failures() -> None:
    with InterpretedExecutor(target(), SOURCES, TIME_LIMIT_SECONDS) as executor:
        refused = executor.execute(b"refuse this")
        violated = executor.execute(b"violate this").failure
        crashed = executor.execute(b"crash this").failure
        hung = executor.execute(b"hang here").failure

    assert refused.failure is None
    assert violated is not None and violated.kind is FailureKind.VIOLATION
    assert crashed is not None and crashed.kind is FailureKind.CRASH
    assert crashed.signature == f"ValueError in judged of {Path(__file__).name}"
    assert hung is not None and hung.kind is FailureKind.HANG


def test_an_input_that_runs_new_lines_counts_as_coverage_only_once() -> None:
    with InterpretedExecutor(target(), SOURCES, TIME_LIMIT_SECONDS) as executor:
        first = executor.execute(b"refuse this")
        repeated = executor.execute(b"refuse that")

    assert first.found_coverage
    assert not repeated.found_coverage
