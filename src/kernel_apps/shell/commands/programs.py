from kernel_apps.shell.session import Session
from kernel_apps.shell.words import parse_number
from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.processes.status import (
    COUNTER_BUFFERS,
    COUNTER_CAPABILITIES,
    COUNTER_ENDPOINTS,
    COUNTER_FRAMES_FREE,
    COUNTER_FRAMES_RESERVED,
    COUNTER_FRAMES_USABLE,
    COUNTER_IPC_BYTES,
    COUNTER_OBJECTS,
    COUNTER_PROCESSES,
    COUNTERS,
    REASON_NAMES,
)
from kernel_protocol.services.control import (
    APPLICATION_EXITED,
    APPLICATION_STATE_NAMES,
    SERVICE_STATE_NAMES,
    SYSTEM_STATE_NAMES,
    WAIT_FOREVER,
)

FRAME_BYTES = 4096
MAX_IDENTITY = 0xFFFFFFF
MAX_WAIT_SECONDS = 3600
NANOSECONDS_PER_SECOND = 1000000000
SEPARATOR = " "
USAGE = "the command was not given its arguments"


def application_of(arguments: list[str]) -> int:
    if not arguments:
        raise KernelError(INVALID_ARGUMENT, USAGE)
    return parse_number(arguments[0], MAX_IDENTITY)


def run(session: Session, arguments: list[str]) -> None:
    if not arguments:
        raise KernelError(INVALID_ARGUMENT, USAGE)
    command = SEPARATOR.join(arguments)
    application = session.control.launch(bytes(command, "utf-8"))
    session.write(f"run: application={application} program={arguments[0]}")


def list_processes(session: Session, arguments: list[str]) -> None:
    state, services = session.control.status()
    session.write(f"ps: system={SYSTEM_STATE_NAMES[state]}")
    for service in services:
        session.write(
            f"ps: service={service.name} state={SERVICE_STATE_NAMES[service.state]} "
            f"restarts={service.failures}/{service.restarts} starts={service.starts}"
        )
    for application in session.control.applications():
        outcome = ""
        if application.state == APPLICATION_EXITED:
            outcome = f" reason={REASON_NAMES[application.reason]} value={application.value}"
        session.write(
            f"ps: application={application.identity} "
            f"state={APPLICATION_STATE_NAMES[application.state]}{outcome} "
            f'command="{application.command}"'
        )


def kill(session: Session, arguments: list[str]) -> None:
    application = application_of(arguments)
    session.control.signal(application)
    session.write(f"kill: application={application}")


def wait(session: Session, arguments: list[str]) -> None:
    application = application_of(arguments)
    timeout = WAIT_FOREVER
    if len(arguments) > 1:
        timeout = parse_number(arguments[1], MAX_WAIT_SECONDS) * NANOSECONDS_PER_SECOND
    reason, value = session.control.wait(application, timeout)
    session.write(f"wait: application={application} reason={REASON_NAMES[reason]} value={value}")


def memory(session: Session, arguments: list[str]) -> None:
    counters = session.control.memory()
    if len(counters) != COUNTERS:
        raise KernelError(INVALID_ARGUMENT, "the system reported an unknown set of counters")
    free = counters[COUNTER_FRAMES_FREE]
    session.write(
        f"mem: frames-usable={counters[COUNTER_FRAMES_USABLE]} frames-free={free} "
        f"frames-reserved={counters[COUNTER_FRAMES_RESERVED]} bytes-free={free * FRAME_BYTES}"
    )
    session.write(
        f"mem: processes={counters[COUNTER_PROCESSES]} objects={counters[COUNTER_OBJECTS]} "
        f"capabilities={counters[COUNTER_CAPABILITIES]} endpoints={counters[COUNTER_ENDPOINTS]} "
        f"buffers={counters[COUNTER_BUFFERS]} ipc-bytes={counters[COUNTER_IPC_BYTES]}"
    )
