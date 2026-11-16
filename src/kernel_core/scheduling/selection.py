from kernel_core.processes.lifecycle import (
    BLOCKED,
    DYING,
    NEW,
    READY,
    REAPED,
    RUNNING,
    check_transition,
)
from kernel_protocol.errors.codes import BAD_STATE, INVALID_ARGUMENT, INVALID_HANDLE, KernelError

PRIORITY_LEVELS = 4
HIGHEST_PRIORITY = 0
LOWEST_PRIORITY = PRIORITY_LEVELS - 1
AGING_THRESHOLD = 8
NO_PROCESS = 0


class ScheduledProcess:
    def __init__(self, priority: int) -> None:
        self.base_priority = priority
        self.effective_priority = priority
        self.state = NEW
        self.waited = 0


class Scheduler:
    def __init__(self) -> None:
        self.running = NO_PROCESS
        self._processes: dict[int, ScheduledProcess] = {}
        self._queues: list[list[int]] = [[] for _ in range(PRIORITY_LEVELS)]

    def processes(self) -> list[int]:
        return sorted(self._processes)

    def process(self, handle: int) -> ScheduledProcess:
        if handle not in self._processes:
            raise KernelError(INVALID_HANDLE, "process is not known to the scheduler")
        return self._processes[handle]

    def queued(self, priority: int) -> list[int]:
        return list(self._queues[priority])

    def admit(self, handle: int, priority: int) -> None:
        if handle == NO_PROCESS:
            raise KernelError(INVALID_HANDLE, "the null handle cannot be scheduled")
        if priority < HIGHEST_PRIORITY or priority > LOWEST_PRIORITY:
            raise KernelError(INVALID_ARGUMENT, "priority out of range")
        if handle in self._processes:
            raise KernelError(BAD_STATE, "process already admitted")
        self._processes[handle] = ScheduledProcess(priority)

    def make_ready(self, handle: int) -> None:
        process = self.process(handle)
        if process.state == RUNNING:
            raise KernelError(BAD_STATE, "a running process becomes ready only by selection")
        check_transition(process.state, READY)
        self._enqueue(handle, process)

    def block(self, handle: int) -> None:
        process = self.process(handle)
        check_transition(process.state, BLOCKED)
        process.state = BLOCKED
        self.running = NO_PROCESS

    def exit(self, handle: int) -> None:
        process = self.process(handle)
        check_transition(process.state, DYING)
        if process.state == READY:
            self._queues[process.effective_priority].remove(handle)
        if self.running == handle:
            self.running = NO_PROCESS
        process.state = DYING

    def reap(self, handle: int) -> None:
        process = self.process(handle)
        check_transition(process.state, REAPED)
        del self._processes[handle]

    def select(self) -> int:
        if self.running != NO_PROCESS:
            self._enqueue(self.running, self._processes[self.running])
            self.running = NO_PROCESS
        chosen = self._dequeue_highest()
        if chosen == NO_PROCESS:
            return NO_PROCESS
        self._age_waiting()
        process = self._processes[chosen]
        process.state = RUNNING
        process.effective_priority = process.base_priority
        process.waited = 0
        self.running = chosen
        return chosen

    def _enqueue(self, handle: int, process: ScheduledProcess) -> None:
        process.state = READY
        process.effective_priority = process.base_priority
        process.waited = 0
        self._queues[process.base_priority].append(handle)

    def _dequeue_highest(self) -> int:
        for queue in self._queues:
            if queue:
                return queue.pop(0)
        return NO_PROCESS

    def _age_waiting(self) -> None:
        for priority in range(HIGHEST_PRIORITY + 1, PRIORITY_LEVELS):
            waiting = self._queues[priority]
            kept = []
            for handle in waiting:
                process = self._processes[handle]
                process.waited += 1
                if process.waited < AGING_THRESHOLD:
                    kept.append(handle)
                    continue
                process.waited = 0
                process.effective_priority = priority - 1
                self._queues[priority - 1].append(handle)
            self._queues[priority] = kept
