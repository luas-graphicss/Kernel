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
DONATION_DEPTH = 8
NO_PROCESS = 0


class ScheduledProcess:
    def __init__(self, priority: int) -> None:
        self.base_priority = priority
        self.entitled_priority = priority
        self.effective_priority = priority
        self.state = NEW
        self.waited = 0
        self.waiting_on = NO_PROCESS
        self.donors: list[int] = []


class Scheduler:
    def __init__(self) -> None:
        self.running = NO_PROCESS
        self._processes: dict[int, ScheduledProcess] = {}
        self._queues: list[list[int]] = [[] for _ in range(PRIORITY_LEVELS)]

    def processes(self) -> list[int]:
        return sorted(self._processes)

    def knows(self, handle: int) -> bool:
        return handle in self._processes

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
        self._stop_donating(handle, process)
        self._enqueue(handle, process)

    def block(self, handle: int) -> None:
        process = self.process(handle)
        check_transition(process.state, BLOCKED)
        process.state = BLOCKED
        process.effective_priority = process.entitled_priority
        self.running = NO_PROCESS

    def donate(self, handle: int, target: int) -> None:
        process = self.process(handle)
        if process.state != BLOCKED:
            raise KernelError(BAD_STATE, "only a blocked process donates its priority")
        if target == handle or target not in self._processes:
            raise KernelError(INVALID_HANDLE, "donation target is not another known process")
        if self._processes[target].state == DYING:
            raise KernelError(INVALID_HANDLE, "donation target is already dying")
        if process.waiting_on != NO_PROCESS:
            raise KernelError(BAD_STATE, "process already donates its priority")
        process.waiting_on = target
        self._processes[target].donors.append(handle)
        self._propagate(target)

    def exit(self, handle: int) -> None:
        process = self.process(handle)
        check_transition(process.state, DYING)
        if process.state == READY:
            self._queues[process.effective_priority].remove(handle)
        if self.running == handle:
            self.running = NO_PROCESS
        self._stop_donating(handle, process)
        for donor in process.donors:
            self._processes[donor].waiting_on = NO_PROCESS
        process.donors = []
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
        process.effective_priority = process.entitled_priority
        process.waited = 0
        self.running = chosen
        return chosen

    def _entitlement(self, process: ScheduledProcess) -> int:
        priority = process.base_priority
        for donor in process.donors:
            donated = self._processes[donor].effective_priority
            if donated < priority:
                priority = donated
        return priority

    def _stop_donating(self, handle: int, process: ScheduledProcess) -> None:
        target = process.waiting_on
        if target == NO_PROCESS:
            return
        process.waiting_on = NO_PROCESS
        self._processes[target].donors.remove(handle)
        self._propagate(target)

    def _propagate(self, handle: int) -> None:
        for _ in range(DONATION_DEPTH):
            process = self._processes[handle]
            entitled = self._entitlement(process)
            if entitled == process.entitled_priority:
                return
            process.entitled_priority = entitled
            if process.state != READY:
                process.effective_priority = entitled
            elif entitled < process.effective_priority:
                self._promote(handle, process, entitled)
            handle = process.waiting_on
            if handle == NO_PROCESS:
                return

    def _promote(self, handle: int, process: ScheduledProcess, priority: int) -> None:
        self._queues[process.effective_priority].remove(handle)
        process.effective_priority = priority
        process.waited = 0
        self._queues[priority].append(handle)

    def _enqueue(self, handle: int, process: ScheduledProcess) -> None:
        process.state = READY
        process.entitled_priority = self._entitlement(process)
        process.effective_priority = process.entitled_priority
        process.waited = 0
        self._queues[process.effective_priority].append(handle)

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
