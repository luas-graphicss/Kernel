from kernel_client import ipc, processes
from suites.scheduling.protocol import OPERATION_REPORT, announce, plain
from suites.support.raw import WORD_BYTES, read_word


def main() -> bool:
    startup = processes.Startup()
    reports = startup.handles[0]
    window = ipc.receive(announce(reports)).message.payload
    start = read_word(window, 0)
    end = read_word(window, WORD_BYTES)
    while processes.clock() < start:
        continue
    turns = 0
    while processes.clock() < end:
        turns += 1
    ipc.send(reports, plain(OPERATION_REPORT, turns, startup.argument))
    return True
