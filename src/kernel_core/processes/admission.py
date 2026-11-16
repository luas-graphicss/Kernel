from kernel_core.memory.budget import ResourceProfile
from kernel_core.processes.accounting import ResourceLedger
from kernel_core.scheduling.selection import Scheduler
from kernel_protocol.errors.codes import INVALID_ARGUMENT, LIMIT_EXCEEDED, KernelError
from kernel_protocol.identity.handles import GENERATION_BITS, HandleTable


class ImageRequest:
    def __init__(
        self, file_bytes: int, memory_bytes: int, heap_bytes: int, stack_bytes: int
    ) -> None:
        if file_bytes < 1 or memory_bytes < file_bytes or heap_bytes < 0 or stack_bytes < 0:
            raise KernelError(INVALID_ARGUMENT, "image sizes are inconsistent")
        self.file_bytes = file_bytes
        self.memory_bytes = memory_bytes
        self.heap_bytes = heap_bytes
        self.stack_bytes = stack_bytes


class ProcessRegistry:
    def __init__(self, profile: ResourceProfile, process_memory_bytes: int) -> None:
        self._heap_limit = profile.process_heap_bytes
        self._account_limits = (
            process_memory_bytes,
            profile.capabilities_per_process,
            profile.ipc_pending_bytes_per_process,
        )
        self._handles = HandleTable(profile.processes, GENERATION_BITS)
        self._ledger = ResourceLedger(
            (
                process_memory_bytes,
                profile.processes * profile.capabilities_per_process,
                profile.ipc_pending_bytes_global,
            ),
            profile.processes,
        )
        self.scheduler = Scheduler()

    def live(self) -> int:
        return self._handles.live

    def memory_in_use(self) -> int:
        return self._ledger.global_usage[0]

    def admit(self, request: ImageRequest, priority: int) -> int:
        if request.heap_bytes > self._heap_limit:
            raise KernelError(LIMIT_EXCEEDED, "declared heap exceeds the heap limit of a process")
        handle = self._handles.allocate()
        self._ledger.open_account(handle, self._account_limits)
        try:
            self._ledger.charge(handle, (request.memory_bytes, 0, 0))
            self.scheduler.admit(handle, priority)
        except KernelError:
            self._ledger.close_account(handle)
            self._handles.release(handle)
            raise
        self.scheduler.make_ready(handle)
        return handle

    def reap(self, handle: int) -> None:
        self.scheduler.exit(handle)
        self.scheduler.reap(handle)
        self._ledger.close_account(handle)
        self._handles.release(handle)
