OK = 0
INVALID_ARGUMENT = 1
INVALID_HANDLE = 2
BAD_STATE = 3
LIMIT_EXCEEDED = 4
BAD_ADDRESS = 5
MESSAGE_TOO_LARGE = 6
UNSUPPORTED = 7
ACCESS_DENIED = 8
TIMED_OUT = 9
CANCELLED = 10
PEER_CLOSED = 11
OUT_OF_MEMORY = 12
WOULD_DEADLOCK = 13

NAMES = (
    "OK",
    "INVALID_ARGUMENT",
    "INVALID_HANDLE",
    "BAD_STATE",
    "LIMIT_EXCEEDED",
    "BAD_ADDRESS",
    "MESSAGE_TOO_LARGE",
    "UNSUPPORTED",
    "ACCESS_DENIED",
    "TIMED_OUT",
    "CANCELLED",
    "PEER_CLOSED",
    "OUT_OF_MEMORY",
    "WOULD_DEADLOCK",
)


class KernelError(Exception):
    def __init__(self, code: int, detail: str) -> None:
        super().__init__(code, detail)
        self.code = code
        self.detail = detail


def error_name(code: int) -> str:
    if code < 0 or code >= len(NAMES):
        raise KernelError(INVALID_ARGUMENT, "unknown error code")
    return NAMES[code]
