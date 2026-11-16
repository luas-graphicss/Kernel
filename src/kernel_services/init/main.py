ALLOCATION_ROUNDS = 4096
BLOCK_BYTES = 1024
RETAINED_BLOCKS = 16
BYTE_MASK = 0xFF
CHECKSUM_MASK = 0xFFFFFFFF
CHECKSUM_MULTIPLIER = 31
EXPECTED_CHECKSUM = 4258764792


def churn_heap(rounds: int) -> int:
    retained: list[bytearray] = []
    checksum = 0
    for index in range(rounds):
        block = bytearray(BLOCK_BYTES)
        block[index % BLOCK_BYTES] = index & BYTE_MASK
        retained.append(block)
        if len(retained) > RETAINED_BLOCKS:
            oldest = retained.pop(0)
            checksum = (checksum * CHECKSUM_MULTIPLIER + sum(oldest)) & CHECKSUM_MASK
    return checksum


def main() -> bool:
    print("init: runtime=micropython privilege=user")
    checksum = churn_heap(ALLOCATION_ROUNDS)
    print(
        f"init: allocated-bytes={ALLOCATION_ROUNDS * BLOCK_BYTES} "
        f"checksum={checksum} expected={EXPECTED_CHECKSUM}"
    )
    return checksum == EXPECTED_CHECKSUM
