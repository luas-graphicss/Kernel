import sys

from kernel_apps import runtime
from kernel_client import capabilities, devices, ipc, power, processes, services
from kernel_protocol.errors.codes import KernelError
from kernel_protocol.identity.handles import FIRST_GENERATION, pack_handle
from kernel_protocol.identity.rights import OBJECT_ENDPOINT, RIGHT_SEND
from kernel_protocol.services.control import (
    OPERATION_LAUNCH,
    OPERATION_POWER,
    OPERATION_STATUS,
    encode_action,
)
from kernel_protocol.services.files import OPEN_CREATE, OPEN_WRITE
from kernel_protocol.system.power import POWER_ACTION_SHUTDOWN

TABLE_SLOTS = 128
GENERATIONS = 8
GUESSED_HANDLES = 48
CALL_PATIENCE_NANOSECONDS = 200000000
SHELL_MODULES = ("kernel_apps.shell.main", "kernel_apps.shell.session")
PROGRAM = "kernel_apps.shell.main"
SCRATCH = b"data/authority.tmp"
CONTROL_REQUESTS = (
    (OPERATION_STATUS, b""),
    (OPERATION_LAUNCH, b"x"),
    (OPERATION_POWER, encode_action(POWER_ACTION_SHUTDOWN)),
)


def refused(operation, *arguments) -> bool:
    try:
        operation(*arguments)
    except KernelError:
        return True
    return False


def table_handles() -> list[int]:
    return [
        pack_handle(index, generation)
        for generation in range(FIRST_GENERATION, FIRST_GENERATION + GENERATIONS)
        for index in range(TABLE_SLOTS)
    ]


def held() -> list[tuple[int, int, int]]:
    found: list[tuple[int, int, int]] = []
    known: list[int] = []
    for handle in table_handles() + list(processes.Startup().handles):
        if handle in known:
            continue
        try:
            kind, rights, _depth = capabilities.inspect(handle)
        except KernelError:
            continue
        known.append(handle)
        found.append((handle, kind, rights))
    return found


def administers_nothing(handles: list[int]) -> bool:
    for handle in handles:
        if not refused(processes.spawn, handle, PROGRAM):
            return False
        if not refused(devices.list_devices, handle) or not refused(devices.claim, handle, 1):
            return False
        if not refused(power.request_shutdown, handle):
            return False
    return True


def controls_nothing(handles: list[int]) -> bool:
    for handle in handles:
        for operation, payload in CONTROL_REQUESTS:
            deadline = processes.clock() + CALL_PATIENCE_NANOSECONDS
            if not refused(services.call, handle, operation, payload, ipc.NO_TRANSFER, deadline):
                return False
    return True


def writes(namespace) -> bool:
    try:
        namespace.open(SCRATCH, OPEN_WRITE | OPEN_CREATE).close()
        namespace.remove(SCRATCH)
    except KernelError:
        return False
    return True


def main() -> bool:
    application = runtime.current()
    holdings = held()
    handles = [handle for handle, _kind, _rights in holdings]
    only_endpoints = len(holdings) != 0 and all(
        kind == OBJECT_ENDPOINT and rights == RIGHT_SEND for _handle, kind, rights in holdings
    )
    is_refused = administers_nothing(handles + list(range(1, GUESSED_HANDLES))) and (
        controls_nothing(handles)
    )
    shell_state = len([name for name in SHELL_MODULES if name in sys.modules])
    namespace = application.files
    print(
        f"authority: capabilities={len(holdings)} "
        f"send-only-endpoints={1 if only_endpoints else 0} "
        f"administration={'refused' if is_refused else 'reached'} "
        f"shell-modules={shell_state} "
        f"files={'none' if namespace is None else ('read-write' if writes(namespace) else 'read')} "
        f"network={'none' if application.network is None else 'granted'}"
    )
    return True
