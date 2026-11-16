from kernel_client import ipc, processes
from suites.scheduling.protocol import OPERATION_NOTE, plain

TICKS = 10


def main() -> bool:
    ticks = processes.Startup().handles[0]
    for tick in range(TICKS):
        ipc.send(ticks, plain(OPERATION_NOTE, tick))
        processes.yield_now()
    return True
