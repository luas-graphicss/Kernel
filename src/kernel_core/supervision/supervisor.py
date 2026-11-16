import _supervisor
from kernel_core.events.outcomes import (
    EVENT_EXITED,
    EVENT_READY,
    NATIVE_BLOCKED,
    NATIVE_DYING,
    NATIVE_FREE,
    RUN_BLOCKED,
    RUN_EXITED,
    RUN_NAMES,
    RUN_SPAWN,
    RUN_STALE,
)
from kernel_core.processes.admission import NO_PARENT, ProcessQuota, ProcessRegistry
from kernel_core.processes.lifecycle import BLOCKED
from kernel_core.scheduling.selection import NO_PROCESS
from kernel_protocol.errors.codes import LIMIT_EXCEEDED, KernelError
from kernel_protocol.processes.status import WAIT_REASON_KILLED

QUANTUM_NANOSECONDS = 10000000
QUOTA_SLACK_FRAMES = 16
TRACE_LIMIT = 64


class Exit:
    def __init__(self, reason: int, value: int) -> None:
        self.reason = reason
        self.value = value


class Supervisor:
    def __init__(self, registry: ProcessRegistry, frame_bytes: int, traces: bool) -> None:
        self._registry = registry
        self._scheduler = registry.scheduler
        self._frame_bytes = frame_bytes
        self._traces_left = TRACE_LIMIT if traces else 0
        self._init = NO_PROCESS
        self.init_exit = Exit(WAIT_REASON_KILLED, 0)
        self.deadlocks = 0

    def start_init(self, program: str, priority: int) -> int:
        quota = self._quota(0, 0, priority, NO_PARENT)
        handle = _supervisor.spawn(
            program,
            0,
            quota.memory_bytes // self._frame_bytes,
            quota.capabilities,
            quota.ipc_pending_bytes,
        )
        if handle < 0:
            raise KernelError(-handle, "the first process could not be created")
        self._registry.admit(handle, quota, priority)
        self._init = handle
        return handle

    def run(self) -> None:
        while self._registry.live() > 0:
            self._drain_events()
            handle = self._scheduler.select()
            if handle != NO_PROCESS:
                result, value, detail = _supervisor.run(handle, QUANTUM_NANOSECONDS)
                self._trace(handle, result)
                self._dispatch(handle, result, value, detail)
            elif self._registry.live() > 0:
                self._wait_for_work()

    def _quota(
        self, heap_bytes: int, memory_bytes: int, priority: int, parent_priority: int
    ) -> ProcessQuota:
        footprint = _supervisor.footprint(heap_bytes)
        if footprint == 0:
            raise KernelError(LIMIT_EXCEEDED, "the requested heap does not fit a process")
        committed = (footprint + QUOTA_SLACK_FRAMES) * self._frame_bytes + memory_bytes
        return self._registry.quota(committed, heap_bytes, priority, parent_priority)

    def _dispatch(self, handle: int, result: int, value: int, detail: int) -> None:
        if result == RUN_BLOCKED:
            self._scheduler.block(handle)
            if value != NO_PROCESS and self._scheduler.knows(value):
                self._scheduler.donate(handle, value)
        elif result == RUN_EXITED:
            self._finish(handle, Exit(value, detail))
        elif result == RUN_SPAWN:
            self._admit_spawn(handle)
        elif result == RUN_STALE:
            self._reconcile(handle)

    def _admit_spawn(self, requester: int) -> None:
        pending = _supervisor.pending_spawn()
        if pending is None:
            return
        _requester, _name, priority, heap_bytes, memory_bytes, _grants = pending
        parent_priority = self._scheduler.process(requester).base_priority
        try:
            quota = self._quota(heap_bytes, memory_bytes, priority, parent_priority)
        except KernelError as error:
            _supervisor.reject_spawn(error.code)
            return
        child = _supervisor.admit_spawn(
            quota.memory_bytes // self._frame_bytes, quota.capabilities, quota.ipc_pending_bytes
        )
        if child > 0:
            self._registry.admit(child, quota, priority)

    def _drain_events(self) -> None:
        if _supervisor.events_overflowed():
            self._resynchronize()
        while True:
            event = _supervisor.next_event()
            if event is None:
                return
            kind, handle = event
            if not self._scheduler.knows(handle):
                continue
            if kind == EVENT_READY:
                self._wake(handle)
            elif kind == EVENT_EXITED:
                self._finish(handle, Exit(WAIT_REASON_KILLED, 0))

    def _wake(self, handle: int) -> None:
        if self._scheduler.process(handle).state == BLOCKED:
            self._scheduler.make_ready(handle)

    def _finish(self, handle: int, outcome: Exit) -> None:
        self._registry.reap(handle)
        _supervisor.release(handle)
        if handle == self._init:
            self.init_exit = outcome
            self._stop_everything()

    def _stop_everything(self) -> None:
        for handle in self._scheduler.processes():
            _supervisor.kill(handle)
            self._registry.reap(handle)
            _supervisor.release(handle)

    def _wait_for_work(self) -> None:
        if _supervisor.idle():
            return
        self.deadlocks += 1
        self._stop_everything()

    def _reconcile(self, handle: int) -> None:
        state = _supervisor.process_state(handle)
        if state in (NATIVE_FREE, NATIVE_DYING):
            self._finish(handle, Exit(WAIT_REASON_KILLED, 0))
        elif state == NATIVE_BLOCKED:
            self._scheduler.block(handle)

    def _resynchronize(self) -> None:
        for handle in self._scheduler.processes():
            if not self._scheduler.knows(handle):
                continue
            state = _supervisor.process_state(handle)
            if state in (NATIVE_FREE, NATIVE_DYING):
                self._finish(handle, Exit(WAIT_REASON_KILLED, 0))
            elif state != NATIVE_BLOCKED:
                self._wake(handle)

    def _trace(self, handle: int, result: int) -> None:
        if self._traces_left == 0:
            return
        self._traces_left -= 1
        priority = self._scheduler.process(handle).effective_priority
        print(f"sched: run={handle} priority={priority} result={RUN_NAMES[result]}")
