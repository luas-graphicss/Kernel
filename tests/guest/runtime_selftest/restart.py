RETAINED_BLOCKS = 256
BLOCK_BYTES = 512

retained: list[bytearray] = []


def main() -> bool:
    import kernel_core.scheduling.selection

    for _ in range(RETAINED_BLOCKS):
        retained.append(bytearray(BLOCK_BYTES))
    scheduler = kernel_core.scheduling.selection.Scheduler()
    return len(retained) == RETAINED_BLOCKS and scheduler.processes() == []
