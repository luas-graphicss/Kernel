BLOCK_BYTES = 2048
KEPT_BLOCKS = 16


def main() -> bool:
    kept = []
    while True:
        kept.append(bytearray(BLOCK_BYTES))
        if len(kept) > KEPT_BLOCKS:
            kept.pop(0)
