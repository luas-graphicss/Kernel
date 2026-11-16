from kernel_protocol.errors.codes import OK, KernelError
from kernel_protocol.processes.status import WAIT_REASON_EXIT, WAIT_REASON_FAULT, WAIT_REASON_KILLED

EXITED_CLEANLY = (WAIT_REASON_EXIT, 0)
EXITED_FAILING = (WAIT_REASON_EXIT, 1)
KILLED = (WAIT_REASON_KILLED, 0)

INSTRUCTION_PAGE_FAULT = 12
LOAD_PAGE_FAULT = 13
STORE_PAGE_FAULT = 15


def faulted(cause: int) -> tuple[int, int]:
    return (WAIT_REASON_FAULT, cause)


def error_code(operation, *arguments) -> int:
    try:
        operation(*arguments)
    except KernelError as error:
        return error.code
    return OK
