from kernel_core.memory.budget import ResourceProfile
from kernel_core.processes.accounting import ResourceLedger
from kernel_core.scheduling.selection import HIGHEST_PRIORITY, LOWEST_PRIORITY, Scheduler
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    LIMIT_EXCEEDED,
    KernelError,
)

NO_PARENT = -1


class ProcessQuota:
    def __init__(self, memory_bytes: int, capabilities: int, ipc_pending_bytes: int) -> None:
        self.memory_bytes = memory_bytes
        self.capabilities = capabilities
        self.ipc_pending_bytes = ipc_pending_bytes


class ProcessRegistry:
    def __init__(self, profile: ResourceProfile, memory_budget_bytes: int) -> None:
        self._heap_limit = profile.process_heap_bytes
        self._capabilities = profile.capabilities_per_process
        self._ipc_pending_bytes = profile.ipc_pending_bytes_per_process
        self._capacity = profile.processes
        self._account_limits = (
            memory_budget_bytes,
            profile.capabilities_per_process,
            profile.ipc_pending_bytes_per_process,
        )
        self._ledger = ResourceLedger(
            (
                memory_budget_bytes,
                profile.processes * profile.capabilities_per_process,
                profile.ipc_pending_bytes_global,
            ),
            profile.processes,
        )
        self._live = 0
        self.scheduler = Scheduler()

    def live(self) -> int:
        return self._live

    def memory_in_use(self) -> int:
        return self._ledger.global_usage[0]

    def quota(
        self, memory_bytes: int, heap_bytes: int, priority: int, parent_priority: int
    ) -> ProcessQuota:
        if memory_bytes < 1 or heap_bytes < 0:
            raise KernelError(INVALID_ARGUMENT, "process sizes are inconsistent")
        if priority < HIGHEST_PRIORITY or priority > LOWEST_PRIORITY:
            raise KernelError(INVALID_ARGUMENT, "priority out of range")
        if parent_priority != NO_PARENT and priority < parent_priority:
            raise KernelError(ACCESS_DENIED, "a process cannot start a more urgent process")
        if heap_bytes > self._heap_limit:
            raise KernelError(LIMIT_EXCEEDED, "declared heap exceeds the heap limit of a process")
        if self._live >= self._capacity:
            raise KernelError(LIMIT_EXCEEDED, "process capacity reached")
        if self._ledger.global_usage[0] + memory_bytes > self._ledger.global_limits[0]:
            raise KernelError(LIMIT_EXCEEDED, "memory budget exceeded")
        return ProcessQuota(memory_bytes, self._capabilities, self._ipc_pending_bytes)

    def admit(self, handle: int, quota: ProcessQuota, priority: int) -> None:
        self._ledger.open_account(handle, self._account_limits)
        try:
            self._ledger.charge(handle, (quota.memory_bytes, 0, 0))
            self.scheduler.admit(handle, priority)
        except KernelError:
            self._ledger.close_account(handle)
            raise
        self._live += 1
        self.scheduler.make_ready(handle)

    def reap(self, handle: int) -> None:
        self.scheduler.exit(handle)
        self.scheduler.reap(handle)
        self._ledger.close_account(handle)
        self._live -= 1
