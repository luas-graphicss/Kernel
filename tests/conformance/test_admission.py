import pytest

from kernel_core.memory.budget import ResourceProfile
from kernel_core.processes.admission import NO_PARENT, ProcessQuota, ProcessRegistry
from kernel_core.processes.lifecycle import READY, RUNNING
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    BAD_STATE,
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    LIMIT_EXCEEDED,
    KernelError,
)

MIB = 1 << 20
BUDGET_BYTES = 8 * MIB
PROCESSES = 3
PRIORITY = 1
CAPABILITIES = 128
IPC_PENDING_BYTES = MIB
HEAP_LIMIT_BYTES = 4 * MIB
FIRST, SECOND = 0x1000000, 0x1000001


def registry() -> ProcessRegistry:
    profile = ResourceProfile(
        (256 * MIB, PROCESSES, 8 * MIB, HEAP_LIMIT_BYTES, CAPABILITIES, IPC_PENDING_BYTES, 16 * MIB)
    )
    return ProcessRegistry(profile, BUDGET_BYTES)


def quota(
    processes: ProcessRegistry,
    memory_bytes: int = 2 * MIB,
    heap_bytes: int = MIB,
    priority: int = PRIORITY,
    parent_priority: int = NO_PARENT,
) -> ProcessQuota:
    return processes.quota(memory_bytes, heap_bytes, priority, parent_priority)


def admit(processes: ProcessRegistry, handle: int, memory_bytes: int = 2 * MIB) -> None:
    processes.admit(handle, quota(processes, memory_bytes), PRIORITY)


def code_of(raised: pytest.ExceptionInfo[KernelError]) -> int:
    return raised.value.code


def test_quota_carries_the_request_and_the_limits_of_the_profile() -> None:
    granted = quota(registry())

    assert granted.memory_bytes == 2 * MIB
    assert granted.capabilities == CAPABILITIES
    assert granted.ipc_pending_bytes == IPC_PENDING_BYTES


def test_admitted_process_is_ready_and_charged() -> None:
    processes = registry()

    admit(processes, FIRST)

    assert processes.live() == 1
    assert processes.memory_in_use() == 2 * MIB
    assert processes.scheduler.process(FIRST).state == READY
    assert processes.scheduler.select() == FIRST
    assert processes.scheduler.process(FIRST).state == RUNNING


def test_reaping_returns_every_resource() -> None:
    processes = registry()
    admit(processes, FIRST)
    processes.scheduler.select()

    processes.reap(FIRST)

    assert processes.live() == 0
    assert processes.memory_in_use() == 0
    with pytest.raises(KernelError) as raised:
        processes.scheduler.process(FIRST)
    assert code_of(raised) == INVALID_HANDLE


def test_declared_heap_above_the_process_limit_is_refused() -> None:
    processes = registry()

    with pytest.raises(KernelError) as raised:
        quota(processes, memory_bytes=6 * MIB, heap_bytes=HEAP_LIMIT_BYTES + 1)

    assert code_of(raised) == LIMIT_EXCEEDED
    assert processes.live() == 0
    assert processes.memory_in_use() == 0


def test_request_above_the_remaining_budget_is_refused_without_a_charge() -> None:
    processes = registry()
    admit(processes, FIRST, memory_bytes=5 * MIB)

    with pytest.raises(KernelError) as raised:
        quota(processes, memory_bytes=4 * MIB)

    assert code_of(raised) == LIMIT_EXCEEDED
    assert processes.live() == 1
    assert processes.memory_in_use() == 5 * MIB
    assert quota(processes, memory_bytes=3 * MIB).memory_bytes == 3 * MIB


@pytest.mark.parametrize("priority", [-1, 4, 99])
def test_priority_outside_the_levels_is_refused(priority: int) -> None:
    with pytest.raises(KernelError) as raised:
        quota(registry(), priority=priority)

    assert code_of(raised) == INVALID_ARGUMENT


def test_child_cannot_be_more_urgent_than_its_parent() -> None:
    processes = registry()

    with pytest.raises(KernelError) as raised:
        quota(processes, priority=0, parent_priority=1)

    assert code_of(raised) == ACCESS_DENIED
    assert quota(processes, priority=1, parent_priority=1).memory_bytes == 2 * MIB
    assert quota(processes, priority=3, parent_priority=1).memory_bytes == 2 * MIB


def test_process_count_is_bounded_by_the_profile() -> None:
    processes = registry()
    for handle in range(FIRST, FIRST + PROCESSES):
        admit(processes, handle, memory_bytes=MIB)

    with pytest.raises(KernelError) as raised:
        quota(processes, memory_bytes=MIB)

    assert code_of(raised) == LIMIT_EXCEEDED
    assert processes.live() == PROCESSES
    assert processes.memory_in_use() == PROCESSES * MIB


@pytest.mark.parametrize(("memory_bytes", "heap_bytes"), [(0, 0), (-MIB, 0), (MIB, -1)])
def test_inconsistent_sizes_are_rejected(memory_bytes: int, heap_bytes: int) -> None:
    with pytest.raises(KernelError) as raised:
        quota(registry(), memory_bytes=memory_bytes, heap_bytes=heap_bytes)

    assert code_of(raised) == INVALID_ARGUMENT


def test_admitting_a_handle_twice_changes_nothing() -> None:
    processes = registry()
    admit(processes, FIRST)

    with pytest.raises(KernelError) as raised:
        admit(processes, FIRST)

    assert code_of(raised) == BAD_STATE
    assert processes.live() == 1
    assert processes.memory_in_use() == 2 * MIB


@pytest.mark.parametrize(
    ("handle", "priority", "code"), [(SECOND, 99, INVALID_ARGUMENT), (0, PRIORITY, INVALID_HANDLE)]
)
def test_admission_the_scheduler_refuses_is_rolled_back(
    handle: int, priority: int, code: int
) -> None:
    processes = registry()
    admit(processes, FIRST)

    with pytest.raises(KernelError) as raised:
        processes.admit(handle, quota(processes), priority)

    assert code_of(raised) == code
    assert processes.live() == 1
    assert processes.memory_in_use() == 2 * MIB
    assert processes.scheduler.processes() == [FIRST]
