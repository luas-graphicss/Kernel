from kernel_core.events.outcomes import (
    NATIVE_BLOCKED,
    NATIVE_FREE,
    NATIVE_READY,
    RUN_BLOCKED,
    RUN_EXITED,
    RUN_SPAWN,
)

FIRST_HANDLE = 0x1000000
FOOTPRINT_FRAMES = 100
NO_GRANTS = 0
STATE_AFTER = {RUN_BLOCKED: NATIVE_BLOCKED, RUN_EXITED: NATIVE_FREE}


class Turn:
    def __init__(self, result, value=0, detail=0, events=(), spawn=None, state=None) -> None:
        self.result = result
        self.value = value
        self.detail = detail
        self.events = events
        self.spawn = spawn
        self.state = state


class NativeSupervisor:
    CALLS = (
        "footprint",
        "spawn",
        "run",
        "pending_spawn",
        "admit_spawn",
        "reject_spawn",
        "next_event",
        "events_overflowed",
        "idle",
        "kill",
        "release",
        "process_state",
    )

    def __init__(self) -> None:
        self.footprint_frames = FOOTPRINT_FRAMES
        self.spawn_error = 0
        self.admission_error = 0
        self.overflowed = False
        self.states: dict[int, int] = {}
        self.events: list[tuple[int, int]] = []
        self.interrupts: list = []
        self.spawned: list[tuple] = []
        self.admitted: list[tuple[int, int, int]] = []
        self.rejected: list[int] = []
        self.ran: list[int] = []
        self.quanta: set[int] = set()
        self.killed: list[int] = []
        self.released: list[int] = []
        self._turns: dict[int, list[Turn]] = {}
        self._pending = None
        self._next_handle = FIRST_HANDLE

    def script(self, handle: int, *turns: Turn) -> None:
        self._turns[handle] = list(turns)

    def footprint(self, heap_bytes: int) -> int:
        return self.footprint_frames

    def spawn(self, program, heap_bytes, memory_frames, capabilities, ipc_pending_bytes) -> int:
        if self.spawn_error:
            return -self.spawn_error
        self.spawned.append((program, heap_bytes, memory_frames, capabilities, ipc_pending_bytes))
        return self._create()

    def run(self, handle: int, quantum_nanoseconds: int) -> tuple[int, int, int]:
        turn = self._turns[handle].pop(0)
        self.ran.append(handle)
        self.quanta.add(quantum_nanoseconds)
        self.events.extend(turn.events)
        if turn.result == RUN_SPAWN:
            self._pending = (handle, *turn.spawn, NO_GRANTS)
        if turn.state is None:
            self.states[handle] = STATE_AFTER.get(turn.result, NATIVE_READY)
        else:
            self.states[handle] = turn.state
        return turn.result, turn.value, turn.detail

    def pending_spawn(self):
        return self._pending

    def admit_spawn(self, memory_frames: int, capabilities: int, ipc_pending_bytes: int) -> int:
        self._pending = None
        self.admitted.append((memory_frames, capabilities, ipc_pending_bytes))
        if self.admission_error:
            return -self.admission_error
        return self._create()

    def reject_spawn(self, error: int) -> None:
        self._pending = None
        self.rejected.append(error)

    def next_event(self):
        return self.events.pop(0) if self.events else None

    def events_overflowed(self) -> bool:
        overflowed, self.overflowed = self.overflowed, False
        return overflowed

    def idle(self) -> bool:
        if not self.interrupts:
            return False
        self.interrupts.pop(0)()
        return True

    def kill(self, handle: int) -> int:
        self.killed.append(handle)
        self.states[handle] = NATIVE_FREE
        return 0

    def release(self, handle: int) -> int:
        self.released.append(handle)
        self.states.pop(handle, None)
        return 0

    def process_state(self, handle: int) -> int:
        return self.states.get(handle, NATIVE_FREE)

    def _create(self) -> int:
        handle = self._next_handle
        self._next_handle += 1
        self.states[handle] = NATIVE_READY
        return handle
