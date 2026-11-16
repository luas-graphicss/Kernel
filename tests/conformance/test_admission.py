import pytest

from kernel_core.memory.budget import ResourceProfile
from kernel_core.processes.admission import ImageRequest, ProcessRegistry
from kernel_core.processes.lifecycle import READY, RUNNING
from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    LIMIT_EXCEEDED,
    KernelError,
)

MIB = 1 << 20
REGION_BYTES = 8 * MIB
PROCESSES = 3
PRIORITY = 1


def registry() -> ProcessRegistry:
    profile = ResourceProfile((256 * MIB, PROCESSES, 8 * MIB, 4 * MIB, 128, MIB, 16 * MIB))
    return ProcessRegistry(profile, REGION_BYTES)


def request(memory_bytes: int = 2 * MIB, heap_bytes: int = MIB) -> ImageRequest:
    return ImageRequest(64 * 1024, memory_bytes, heap_bytes, 64 * 1024)


def code_of(raised: pytest.ExceptionInfo[KernelError]) -> int:
    return raised.value.code


def test_admitted_process_is_ready_and_charged() -> None:
    processes = registry()

    handle = processes.admit(request(), PRIORITY)

    assert processes.live() == 1
    assert processes.memory_in_use() == 2 * MIB
    assert processes.scheduler.process(handle).state == READY
    assert processes.scheduler.select() == handle
    assert processes.scheduler.process(handle).state == RUNNING


def test_reaping_returns_every_resource() -> None:
    processes = registry()
    handle = processes.admit(request(), PRIORITY)
    processes.scheduler.select()

    processes.reap(handle)

    assert processes.live() == 0
    assert processes.memory_in_use() == 0
    with pytest.raises(KernelError) as raised:
        processes.scheduler.process(handle)
    assert code_of(raised) == INVALID_HANDLE


def test_reaped_handle_is_never_issued_again() -> None:
    processes = registry()
    first = processes.admit(request(), PRIORITY)
    processes.reap(first)

    second = processes.admit(request(), PRIORITY)

    assert second != first
    with pytest.raises(KernelError) as raised:
        processes.reap(first)
    assert code_of(raised) == INVALID_HANDLE


def test_declared_heap_above_the_process_limit_is_refused() -> None:
    processes = registry()

    with pytest.raises(KernelError) as raised:
        processes.admit(request(memory_bytes=6 * MIB, heap_bytes=4 * MIB + 1), PRIORITY)

    assert code_of(raised) == LIMIT_EXCEEDED
    assert processes.live() == 0
    assert processes.memory_in_use() == 0


def test_refused_admission_leaves_no_partial_state() -> None:
    processes = registry()
    processes.admit(request(memory_bytes=5 * MIB), PRIORITY)

    with pytest.raises(KernelError) as raised:
        processes.admit(request(memory_bytes=4 * MIB), PRIORITY)

    assert code_of(raised) == LIMIT_EXCEEDED
    assert processes.live() == 1
    assert processes.memory_in_use() == 5 * MIB
    assert len(processes.scheduler.processes()) == 1
    assert processes.admit(request(memory_bytes=3 * MIB), PRIORITY) != 0


def test_invalid_priority_rolls_the_admission_back() -> None:
    processes = registry()

    with pytest.raises(KernelError) as raised:
        processes.admit(request(), 99)

    assert code_of(raised) == INVALID_ARGUMENT
    assert processes.live() == 0
    assert processes.memory_in_use() == 0


def test_process_count_is_bounded_by_the_profile() -> None:
    processes = registry()
    for _ in range(PROCESSES):
        processes.admit(request(memory_bytes=MIB), PRIORITY)

    with pytest.raises(KernelError) as raised:
        processes.admit(request(memory_bytes=MIB), PRIORITY)

    assert code_of(raised) == LIMIT_EXCEEDED
    assert processes.live() == PROCESSES
    assert processes.memory_in_use() == PROCESSES * MIB


@pytest.mark.parametrize(
    ("file_bytes", "memory_bytes", "heap_bytes", "stack_bytes"),
    [(0, 10, 0, 0), (20, 10, 0, 0), (10, 20, -1, 0), (10, 20, 0, -1)],
)
def test_inconsistent_image_sizes_are_rejected(
    file_bytes: int, memory_bytes: int, heap_bytes: int, stack_bytes: int
) -> None:
    with pytest.raises(KernelError) as raised:
        ImageRequest(file_bytes, memory_bytes, heap_bytes, stack_bytes)

    assert code_of(raised) == INVALID_ARGUMENT
