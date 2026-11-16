import _probe

from kernel_client import ipc, processes
from kernel_protocol.wire.message import Message
from suites.support.raw import word

BLOCK_BYTES = 1024
ROUNDS = 40
BYTE_MASK = 0xFF
ADDRESS_OPERATION = 1
NO_FLAGS = 0


def pattern_of(seed: int) -> bytes:
    return bytes((seed + index) & BYTE_MASK for index in range(BLOCK_BYTES))


def main() -> bool:
    startup = processes.Startup()
    seed = int(str(startup.argument, "ascii"))
    pattern = pattern_of(seed)
    block = bytearray(pattern)
    announcement = Message(ADDRESS_OPERATION, NO_FLAGS, seed, word(_probe.address(block)))
    ipc.send(startup.handles[0], announcement)
    for _ in range(ROUNDS):
        processes.yield_now()
        if bytes(block) != pattern:
            return False
    return True
