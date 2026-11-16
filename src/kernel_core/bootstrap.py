import _supervisor
from kernel_core.memory.budget import ResourceProfile, check_profile, process_budget_bytes
from kernel_core.processes.admission import ProcessRegistry
from kernel_core.supervision.supervisor import Supervisor
from kernel_protocol.errors.codes import KernelError, error_name
from kernel_protocol.processes.status import (
    COUNTER_BUFFERS,
    COUNTER_CAPABILITIES,
    COUNTER_ENDPOINTS,
    COUNTER_FRAMES_FREE,
    COUNTER_IPC_BYTES,
    COUNTER_MESSAGES,
    COUNTER_OBJECTS,
    COUNTER_PROCESSES,
    REASON_NAMES,
    WAIT_REASON_EXIT,
)
from kernel_protocol.wire.spawn import name_is_valid

INIT_PROGRAM = "kernel_services.init.main"
INIT_PRIORITY = 1
INIT_OPTION = "init="
TRACE_OPTION = "trace=schedule"
PROGRAM_READY = "ok"
EXIT_SUCCEEDED = 0
TRACKED_COUNTERS = (
    ("frames-free", COUNTER_FRAMES_FREE),
    ("processes", COUNTER_PROCESSES),
    ("objects", COUNTER_OBJECTS),
    ("capabilities", COUNTER_CAPABILITIES),
    ("endpoints", COUNTER_ENDPOINTS),
    ("messages", COUNTER_MESSAGES),
    ("ipc-bytes", COUNTER_IPC_BYTES),
    ("buffers", COUNTER_BUFFERS),
)


def report(text: str) -> None:
    print("policy: " + text)


def init_program(arguments: str) -> str:
    for option in arguments.split(" "):
        if option.startswith(INIT_OPTION):
            return option[len(INIT_OPTION) :]
    return INIT_PROGRAM


def open_registry() -> tuple[ProcessRegistry, int]:
    profile = ResourceProfile(_supervisor.limits())
    _hart, _memory_base, machine_bytes = _supervisor.machine()
    _region_base, region_bytes = _supervisor.user_region()
    frame_bytes, usable_frames, free_frames, reserve_frames = _supervisor.memory()
    check_profile(profile, machine_bytes, region_bytes)
    report(
        f"profile=ok memory-bytes={profile.memory_bytes} processes={profile.processes} "
        f"supervisor-heap-bytes={profile.supervisor_heap_bytes} "
        f"usable-frames={usable_frames} reserve-frames={reserve_frames}"
    )
    budget = process_budget_bytes(frame_bytes, free_frames, reserve_frames)
    return ProcessRegistry(profile, budget), frame_bytes


def describe_leaks(before: tuple[int, ...], after: tuple[int, ...]) -> str:
    leaks = ""
    for name, index in TRACKED_COUNTERS:
        if before[index] != after[index]:
            leaks += f" {name}={before[index]}->{after[index]}"
    return leaks


def run_init(arguments: str) -> bool:
    program = init_program(arguments)
    if not name_is_valid(program):
        report("rejected=init reason=invalid-program-name")
        return False
    status = _supervisor.prepare_program()
    if status != PROGRAM_READY:
        report(f"rejected=boot-module reason={status}")
        return False
    registry, frame_bytes = open_registry()
    supervisor = Supervisor(registry, frame_bytes, TRACE_OPTION in arguments.split(" "))
    baseline = _supervisor.counters()
    handle = supervisor.start_init(program, INIT_PRIORITY)
    report(f"admitted=init program={program} handle={handle} priority={INIT_PRIORITY}")
    supervisor.run()
    outcome = supervisor.init_exit
    report(
        f"reaped=init reason={REASON_NAMES[outcome.reason]} value={outcome.value} "
        f"live={registry.live()} memory-in-use={registry.memory_in_use()}"
    )
    leaks = describe_leaks(baseline, _supervisor.counters())
    if supervisor.deadlocks:
        report(f"stopped=deadlock occurrences={supervisor.deadlocks}")
    if leaks:
        report(f"resources=leaked{leaks}")
        return False
    report("resources=released")
    return (
        supervisor.deadlocks == 0
        and outcome.reason == WAIT_REASON_EXIT
        and outcome.value == EXIT_SUCCEEDED
    )


def main() -> bool:
    try:
        return run_init(_supervisor.arguments())
    except KernelError as error:
        report(f'rejected=request code={error_name(error.code)} detail="{error.detail}"')
        return False
