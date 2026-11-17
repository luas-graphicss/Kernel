import os
import signal
import traceback
from pathlib import Path
from types import FrameType, TracebackType
from typing import Self

from kernel_tool.fuzzing.coverage import LineCoverage
from kernel_tool.fuzzing.model import (
    Execution,
    Failure,
    FailureKind,
    InterpretedTarget,
    InvariantError,
)

TIME_LIMIT_SIGNATURE = "the input exceeded the time limit"


class ExecutionTimedOut(BaseException):
    pass


def _interrupt(_signal: int, _frame: FrameType | None) -> None:
    raise ExecutionTimedOut


class InterpretedExecutor:
    def __init__(self, target: InterpretedTarget, sources: Path, time_limit_seconds: float) -> None:
        self._target = target
        self._sources = str(sources) + os.sep
        self._time_limit_seconds = time_limit_seconds
        self._coverage = LineCoverage(self._sources)

    def __enter__(self) -> Self:
        signal.signal(signal.SIGALRM, _interrupt)
        self._coverage.start()
        return self

    def __exit__(
        self,
        _kind: type[BaseException] | None,
        _error: BaseException | None,
        _trace: TracebackType | None,
    ) -> None:
        self._coverage.stop()
        signal.signal(signal.SIGALRM, signal.SIG_DFL)

    def execute(self, data: bytes) -> Execution:
        self._coverage.take_fresh()
        try:
            signal.setitimer(signal.ITIMER_REAL, self._time_limit_seconds)
            try:
                failure = self._outcome(data)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
        except ExecutionTimedOut:
            detail = f"no result within {self._time_limit_seconds:g} seconds"
            failure = Failure(FailureKind.HANG, TIME_LIMIT_SIGNATURE, detail)
        return Execution(failure, self._coverage.take_fresh() > 0)

    def _outcome(self, data: bytes) -> Failure | None:
        try:
            self._target.run(data)
        except self._target.refusals:
            return None
        except InvariantError as violation:
            return Failure(FailureKind.VIOLATION, str(violation), str(violation))
        except Exception as error:
            detail = "".join(traceback.format_exception(error))
            return Failure(FailureKind.CRASH, self._signature(error), detail)
        return None

    def _signature(self, error: Exception) -> str:
        frames = [
            frame
            for frame in traceback.extract_tb(error.__traceback__)
            if frame.filename.startswith(self._sources)
        ]
        if not frames:
            return type(error).__name__
        deepest = frames[-1]
        module = deepest.filename.removeprefix(self._sources)
        return f"{type(error).__name__} in {deepest.name} of {module}"
