from corpus.digest import Digest
from corpus.failure import require
from corpus.prng import Generator
from kernel_core.processes.lifecycle import BLOCKED, DYING, NEW, READY, RUNNING
from kernel_core.scheduling.selection import (
    AGING_THRESHOLD,
    LOWEST_PRIORITY,
    NO_PROCESS,
    PRIORITY_LEVELS,
    Scheduler,
)
from kernel_protocol.errors.codes import OK, KernelError
from kernel_protocol.identity.handles import HandleTable

MAX_PROCESSES = 8
GENERATION_BITS = 16
STARVATION_BOUND = LOWEST_PRIORITY * AGING_THRESHOLD + MAX_PROCESSES


def in_state(scheduler: Scheduler, state: int) -> list[int]:
    return [handle for handle in scheduler.processes() if scheduler.process(handle).state == state]


def check_invariants(scheduler: Scheduler, waiting: dict[int, int]) -> None:
    running = in_state(scheduler, RUNNING)
    require(len(running) <= 1, "at most one process runs")
    if running:
        require(scheduler.running == running[0], "the running process is the selected one")
    else:
        require(scheduler.running == NO_PROCESS, "no process is marked running")

    queued_total = 0
    for priority in range(PRIORITY_LEVELS):
        for handle in scheduler.queued(priority):
            process = scheduler.process(handle)
            queued_total += 1
            require(process.state == READY, "only ready processes are queued")
            require(process.effective_priority == priority, "queue matches effective priority")
            require(process.effective_priority <= process.base_priority, "aging only promotes")
            require(process.waited < AGING_THRESHOLD, "aging counter stays below the threshold")
    require(queued_total == len(in_state(scheduler, READY)), "every ready process is queued once")

    for handle in in_state(scheduler, READY):
        require(waiting[handle] <= STARVATION_BOUND, "a ready process is selected within the bound")


def check_donations(scheduler: Scheduler) -> None:
    for handle in scheduler.processes():
        process = scheduler.process(handle)
        require(process.entitled_priority <= process.base_priority, "donation only promotes")
        require(
            process.effective_priority <= process.entitled_priority,
            "a process never runs below its entitlement",
        )
        for donor in process.donors:
            waiter = scheduler.process(donor)
            require(waiter.state == BLOCKED, "only a blocked process donates")
            require(waiter.waiting_on == handle, "a donor waits on the process that lists it")


def apply(digest: Digest, operation, *handles: int) -> bool:
    try:
        operation(*handles)
    except KernelError as error:
        digest.add(error.code)
        return False
    digest.add(OK)
    return True


def run(seed: int, transitions: int) -> str:
    generator = Generator(seed)
    digest = Digest()
    identities = HandleTable(MAX_PROCESSES, GENERATION_BITS)
    scheduler = Scheduler()
    waiting: dict[int, int] = {}

    for _ in range(transitions):
        choice = generator.below(100)
        known = scheduler.processes()
        if choice < 12 and len(known) < MAX_PROCESSES:
            handle = identities.allocate()
            scheduler.admit(handle, generator.below(PRIORITY_LEVELS))
            digest.add(handle)
        elif choice < 30:
            candidates = in_state(scheduler, NEW) + in_state(scheduler, BLOCKED)
            if candidates:
                handle = generator.pick(candidates)
                if apply(digest, scheduler.make_ready, handle):
                    waiting[handle] = 0
        elif choice < 68:
            chosen = scheduler.select()
            digest.add(chosen)
            for handle in in_state(scheduler, READY):
                waiting[handle] = waiting.get(handle, 0) + 1
            if chosen != NO_PROCESS:
                waiting[chosen] = 0
        elif choice < 75:
            waiters = in_state(scheduler, BLOCKED)
            if waiters and len(known) > 1:
                apply(digest, scheduler.donate, generator.pick(waiters), generator.pick(known))
        elif choice < 85:
            if scheduler.running != NO_PROCESS:
                apply(digest, scheduler.block, scheduler.running)
        elif choice < 93 and known:
            apply(digest, scheduler.exit, generator.pick(known))
        elif known:
            handle = generator.pick(known)
            if apply(digest, scheduler.reap, handle):
                identities.release(handle)
        else:
            apply(digest, scheduler.make_ready, generator.next())
        check_invariants(scheduler, waiting)
        check_donations(scheduler)

    digest.add(len(in_state(scheduler, DYING)))
    digest.add(identities.live)
    return digest.hexdigest()
