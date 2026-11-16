import _process
from kernel_protocol.errors.codes import KernelError

FAILURE = "system call failed"


def check(status: int) -> int:
    if status < 0:
        raise KernelError(-status, FAILURE)
    return status


def scalar(number: int, first: int = 0, second: int = 0) -> int:
    return check(_process.call(number, first, second))
