from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    FAILED = 1
    USAGE = 2
    UNAVAILABLE = 3


class ToolError(Exception):
    exit_code = ExitCode.FAILED
    label = "failed"


class CheckError(ToolError):
    pass


class InfrastructureError(ToolError):
    exit_code = ExitCode.UNAVAILABLE
    label = "infrastructure unavailable"
