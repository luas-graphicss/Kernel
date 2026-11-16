from kernel_client import ipc
from kernel_client.processes import Startup
from suites.scheduling.protocol import OPERATION_NOTE, OPERATION_STOP, announce, plain


def main() -> bool:
    reports = Startup().handles[0]
    endpoint = announce(reports)
    while True:
        request = ipc.receive(endpoint)
        if request.message.operation == OPERATION_STOP:
            return True
        ipc.answer(request, b"")
        ipc.send(reports, plain(OPERATION_NOTE))
