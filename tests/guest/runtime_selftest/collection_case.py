import gc

from runtime_selftest.checks import Checks

PRESSURE_ROUNDS = 3072
BLOCK_BYTES = 4096
KEEP_EVERY = 48
BYTE_MASK = 0xFF
BASELINE_SLACK_BYTES = 4096
FREQUENT_THRESHOLD_BYTES = 32768
CHAIN_LENGTH = 2000
DISABLED_THRESHOLD = -1


def stamp(block: bytearray, index: int) -> None:
    block[0] = index & BYTE_MASK
    block[-1] = (index >> 8) & BYTE_MASK


def stamped(block: bytearray, index: int) -> bool:
    return block[0] == index & BYTE_MASK and block[-1] == (index >> 8) & BYTE_MASK


def pressure(checks: Checks) -> None:
    kept = []
    collections = 0
    previous_free = gc.mem_free()
    for index in range(PRESSURE_ROUNDS):
        block = bytearray(BLOCK_BYTES)
        stamp(block, index)
        if index % KEEP_EVERY == 0:
            kept.append((index, block))
        free = gc.mem_free()
        if free > previous_free:
            collections += 1
        previous_free = free
    checks.require(collections >= 1, "allocation pressure triggers automatic collections")
    checks.require(
        all(stamped(block, index) for index, block in kept), "live blocks survive collections"
    )


def build_chain(length: int):
    head = None
    for index in range(length):
        head = (index, [index, index * index], {"next": head})
    return head


def chain_is_intact(head, length: int) -> bool:
    expected = length - 1
    while head is not None:
        index, pair, link = head
        if index != expected or pair != [index, index * index]:
            return False
        head = link["next"]
        expected -= 1
    return expected == -1


def frequent_collections(checks: Checks) -> None:
    gc.threshold(FREQUENT_THRESHOLD_BYTES)
    head = build_chain(CHAIN_LENGTH)
    text = ""
    for index in range(CHAIN_LENGTH):
        text = str(index * 1000003) + text[:32]
    gc.threshold(DISABLED_THRESHOLD)
    checks.require(chain_is_intact(head, CHAIN_LENGTH), "nested containers survive collections")
    checks.require(text.startswith(str((CHAIN_LENGTH - 1) * 1000003)), "temporaries stay valid")


def run(checks: Checks) -> None:
    gc.collect()
    baseline = gc.mem_alloc()
    pressure(checks)
    frequent_collections(checks)
    gc.collect()
    checks.require(
        gc.mem_alloc() <= baseline + BASELINE_SLACK_BYTES,
        "dropped references return the heap to its baseline",
    )
