import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from kernel_tool.outcome import CheckError, InfrastructureError
from kernel_tool.workspace import Workspace


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class Area(StrEnum):
    HOST = "host"
    NATIVE = "native"
    RUNTIME = "runtime"
    EMULATION = "emulation"
    INTEROPERABILITY = "interoperability"
    RECOVERY = "recovery"


type CheckAction = Callable[[Workspace, str], None]


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    area: Area
    run: CheckAction


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    area: Area
    status: Status
    seconds: float
    detail: str


def execute(
    check: Check,
    workspace: Workspace,
    profile: str,
    clock: Callable[[], float] = time.monotonic,
) -> CheckResult:
    started = clock()
    status = Status.PASSED
    detail = ""
    try:
        check.run(workspace, profile)
    except InfrastructureError as error:
        status, detail = Status.INCOMPLETE, str(error)
    except CheckError as error:
        status, detail = Status.FAILED, str(error)
    return CheckResult(check.name, check.area, status, round(clock() - started, 3), detail)


def names_with(results: list[CheckResult], status: Status) -> list[str]:
    return [result.name for result in results if result.status is status]
