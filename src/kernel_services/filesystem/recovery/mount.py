from kernel_protocol.errors.codes import CORRUPTED, OK, UNSUPPORTED, KernelError
from kernel_services.filesystem.format.codec import corrupted
from kernel_services.filesystem.format.layout import FIRST_TREE_BLOCK, MIN_BLOCKS, SUPERBLOCK_SLOTS
from kernel_services.filesystem.format.superblock import Superblock, decode_superblock
from kernel_services.filesystem.recovery.survey import Survey, survey_tree
from kernel_services.filesystem.storage import BlockStore

CLEAN = "clean"
RECOVERED = "recovered"
PREVIOUS_ROOT_DAMAGED = "previous-root-damaged"
NEWEST_ROOT_DAMAGED = "newest-root-damaged"
GENERATION_GAP = "generation-gap"
DEVICE_READ_ONLY = "device-read-only"
DEVICE_WITHOUT_FLUSH = "device-without-flush"
FIRST_GENERATION = 1


class Slot:
    def __init__(self, number: int) -> None:
        self.number = number
        self.superblock: Superblock | None = None
        self.code = OK
        self.problem = ""


class Mounted:
    def __init__(self, survey: Survey, slots: list[Slot]) -> None:
        self.superblock = survey.superblock
        self.survey = survey
        self.slots = slots
        self.retiring: list[int] = []
        self.read_only = False
        self.reason = CLEAN


def read_slot(store: BlockStore, number: int) -> Slot:
    slot = Slot(number)
    try:
        slot.superblock = decode_superblock(store.read(number), number, store)
    except KernelError as error:
        if error.code not in (CORRUPTED, UNSUPPORTED):
            raise
        slot.code = error.code
        slot.problem = error.detail
    return slot


def newest_first(slots: list[Slot]) -> list[Superblock]:
    found = [slot.superblock for slot in slots if slot.superblock is not None]
    if len(found) == SUPERBLOCK_SLOTS and found[0].generation < found[1].generation:
        found.reverse()
    return found


def first_consistent(
    store: BlockStore, slots: list[Slot], candidates: list[Superblock], deep: bool
) -> Survey:
    problems = []
    for candidate in candidates:
        try:
            return survey_tree(store, candidate, deep)
        except KernelError as error:
            if error.code != CORRUPTED:
                raise
            slots[candidate.generation % SUPERBLOCK_SLOTS].problem = error.detail
            problems.append(error.detail)
    raise corrupted("no superblock leads to a consistent tree: " + "; ".join(problems))


def unprotected_blocks(chosen: Survey, previous: Survey) -> list[int]:
    return [
        block
        for block in range(FIRST_TREE_BLOCK, chosen.superblock.total_blocks)
        if previous.reachable.test(block) and not chosen.reachable.test(block)
    ]


def protect_previous(store: BlockStore, mounted: Mounted, previous: Superblock) -> None:
    try:
        mounted.retiring = unprotected_blocks(mounted.survey, survey_tree(store, previous, False))
    except KernelError as error:
        if error.code != CORRUPTED:
            raise
        mounted.slots[previous.generation % SUPERBLOCK_SLOTS].problem = error.detail
        mounted.reason = PREVIOUS_ROOT_DAMAGED


def judge(store: BlockStore, mounted: Mounted, candidates: list[Superblock]) -> None:
    newest = candidates[0]
    chosen = mounted.superblock
    alone = len(candidates) == 1
    if chosen is not newest:
        mounted.read_only = True
        mounted.reason = NEWEST_ROOT_DAMAGED
    elif not alone and newest.generation - candidates[1].generation != 1:
        mounted.read_only = True
        mounted.reason = GENERATION_GAP
    elif alone and chosen.generation != FIRST_GENERATION:
        mounted.reason = RECOVERED
    elif not alone:
        protect_previous(store, mounted, candidates[1])
    if not mounted.read_only and not store.writable:
        mounted.read_only = True
        mounted.reason = DEVICE_READ_ONLY
    elif not mounted.read_only and not store.durable:
        mounted.read_only = True
        mounted.reason = DEVICE_WITHOUT_FLUSH


def mount(store: BlockStore, deep: bool) -> Mounted:
    if store.blocks < MIN_BLOCKS:
        raise corrupted("device is smaller than the smallest volume")
    slots = [read_slot(store, number) for number in range(SUPERBLOCK_SLOTS)]
    if UNSUPPORTED in (slots[0].code, slots[1].code):
        raise KernelError(UNSUPPORTED, "volume uses a format version this system does not know")
    candidates = newest_first(slots)
    if not candidates:
        raise corrupted("device holds no valid superblock")
    mounted = Mounted(first_consistent(store, slots, candidates, deep), slots)
    judge(store, mounted, candidates)
    return mounted
