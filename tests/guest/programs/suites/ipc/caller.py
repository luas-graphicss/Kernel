from kernel_client import ipc
from kernel_client.processes import Startup
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support.expectations import error_code


def call(target: int) -> int:
    return error_code(ipc.call, target, plain(OPERATION_REQUEST))


def send(target: int) -> int:
    return error_code(ipc.send, target, plain(OPERATION_REQUEST))


def receive(_target: int) -> int:
    return error_code(ipc.receive, ipc.create_endpoint())


MODES = {"call": call, "send": send, "receive": receive}
NO_TARGET = 0


def main() -> bool:
    startup = Startup()
    mode, expected = str(startup.argument, "ascii").split(" ")
    target = startup.handles[0] if startup.handles else NO_TARGET
    return MODES[mode](target) == int(expected)
