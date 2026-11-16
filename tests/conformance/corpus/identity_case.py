from corpus.digest import Digest
from corpus.failure import require
from corpus.prng import Generator
from kernel_protocol.errors.codes import OK, KernelError
from kernel_protocol.identity.handles import HandleTable

CAPACITY = 16
GENERATION_BITS = 7
RECENT_STALE_CHECKED = 8


def attempt_resolve(table: HandleTable, handle: int) -> int:
    try:
        table.resolve(handle)
    except KernelError as error:
        return error.code
    return OK


def attempt_release(table: HandleTable, handle: int) -> int:
    try:
        table.release(handle)
    except KernelError as error:
        return error.code
    return OK


def check_invariants(table: HandleTable, live: list[int], stale: list[int]) -> None:
    require(table.live == len(live), "live count matches the handles in use")
    require(
        table.live + table.free_slots() + table.retired == CAPACITY,
        "every slot is live, free or retired",
    )
    for handle in live:
        require(attempt_resolve(table, handle) == OK, "a live handle resolves")
    for handle in stale[-RECENT_STALE_CHECKED:]:
        require(attempt_resolve(table, handle) != OK, "a released handle never resolves")


def run(seed: int, transitions: int) -> str:
    generator = Generator(seed)
    digest = Digest()
    table = HandleTable(CAPACITY, GENERATION_BITS)
    live: list[int] = []
    stale: list[int] = []

    for _ in range(transitions):
        choice = generator.below(100)
        if choice < 40:
            try:
                handle = table.allocate()
            except KernelError as error:
                digest.add(error.code)
            else:
                require(handle not in live, "an allocated handle is unique among live ones")
                live.append(handle)
                digest.add(handle)
        elif choice < 75 and live:
            handle = live.pop(generator.below(len(live)))
            digest.add(attempt_release(table, handle))
            stale.append(handle)
        elif choice < 85 and live:
            digest.add(attempt_resolve(table, generator.pick(live)))
        elif choice < 95 and stale:
            digest.add(attempt_resolve(table, generator.pick(stale)))
        elif stale:
            digest.add(attempt_release(table, generator.pick(stale)))
        else:
            digest.add(attempt_resolve(table, generator.next()))
        check_invariants(table, live, stale)

    for handle in stale:
        require(attempt_resolve(table, handle) != OK, "no released handle resolves at the end")
    digest.add(table.live)
    digest.add(table.retired)
    return digest.hexdigest()
