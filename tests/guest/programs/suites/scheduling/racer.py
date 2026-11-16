from kernel_client import ipc, processes
from suites.scheduling.protocol import OPERATION_REPORT, OPERATION_STOP, announce, plain
from suites.support.expectations import error_code
from suites.support.raw import read_word


def main() -> bool:
    reports = processes.Startup().handles[0]
    endpoint = announce(reports)
    while True:
        request = ipc.receive(endpoint)
        if request.message.operation == OPERATION_STOP:
            return True
        reply_time = read_word(request.message.payload, 0)
        while processes.clock() < reply_time:
            continue
        ipc.send(reports, plain(OPERATION_REPORT, error_code(ipc.answer, request, b"")))
