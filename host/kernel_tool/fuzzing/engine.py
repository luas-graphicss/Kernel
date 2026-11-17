import random
import time
from collections.abc import Callable, Iterable
from typing import Protocol

from kernel_tool.fuzzing.minimization import minimize
from kernel_tool.fuzzing.model import Execution, Failure, Finding, Target, TargetRun
from kernel_tool.fuzzing.mutation import Mutator

MINIMIZATION_ATTEMPTS = 96
MAX_POPULATION = 8192
EMPTY_INPUT = b""


class Executor(Protocol):
    def execute(self, data: bytes) -> Execution: ...


def replay(
    target: Target, executor: Executor, inputs: Iterable[bytes]
) -> tuple[list[bytes], list[Finding]]:
    accepted = []
    findings = []
    for data in dict.fromkeys(inputs):
        failure = executor.execute(data).failure
        if failure is None:
            accepted.append(data)
        else:
            findings.append(Finding(target.family, target.name, failure, data))
    return accepted, findings


def fuzz(
    target: Target,
    executor: Executor,
    inputs: Iterable[bytes],
    budget_seconds: float,
    seed: int,
    clock: Callable[[], float] = time.monotonic,
) -> TargetRun:
    started = clock()
    population, findings = replay(target, executor, inputs)
    executions = len(population) + len(findings)
    if not population:
        population = [EMPTY_INPUT]
    chooser = random.Random(seed)
    mutator = Mutator(chooser, target.max_input_bytes)
    known = {finding.failure.signature for finding in findings}
    discovered = []
    while clock() - started < budget_seconds:
        candidate = mutator.mutate(chooser.choice(population), chooser.choice(population))
        execution = executor.execute(candidate)
        executions += 1
        failure = execution.failure
        if failure is not None:
            if failure.signature not in known:
                known.add(failure.signature)
                smallest = _smallest_failing(executor, candidate, failure)
                findings.append(Finding(target.family, target.name, failure, smallest))
        elif execution.found_coverage and len(population) < MAX_POPULATION:
            population.append(candidate)
            discovered.append(candidate)
    return TargetRun(
        family=target.family,
        target=target.name,
        executions=executions,
        seconds=clock() - started,
        population=len(population),
        discovered=tuple(discovered),
        findings=tuple(findings),
    )


def _smallest_failing(executor: Executor, data: bytes, failure: Failure) -> bytes:
    def fails_the_same_way(candidate: bytes) -> bool:
        repeated = executor.execute(candidate).failure
        return repeated is not None and repeated.signature == failure.signature

    return minimize(data, fails_the_same_way, MINIMIZATION_ATTEMPTS)
