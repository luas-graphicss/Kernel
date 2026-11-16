from kernel_client import capabilities, processes

CHILD_HEAP_BYTES = 0x40000


def start(
    system: int,
    program: str,
    argument: bytes = b"",
    priority: int = processes.DEFAULT_PRIORITY,
    memory_bytes: int = 0,
    grants: tuple[tuple[int, int], ...] = (),
) -> int:
    return processes.spawn(
        system, program, argument, priority, CHILD_HEAP_BYTES, memory_bytes, grants
    )


def finish(child: int) -> tuple[int, int]:
    outcome = processes.wait(child)
    capabilities.close(child)
    return outcome


def stop(child: int) -> tuple[int, int]:
    processes.kill(child)
    return finish(child)


def run(
    system: int,
    program: str,
    argument: bytes = b"",
    priority: int = processes.DEFAULT_PRIORITY,
    memory_bytes: int = 0,
    grants: tuple[tuple[int, int], ...] = (),
) -> tuple[int, int]:
    return finish(start(system, program, argument, priority, memory_bytes, grants))
