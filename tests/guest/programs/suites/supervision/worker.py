from kernel_client import ipc, services
from kernel_client.processes import Startup
from kernel_client.services import Reply, Service
from kernel_protocol.errors.codes import UNSUPPORTED, KernelError
from kernel_protocol.services.lifecycle import OPERATION_STOP, decode_supervisor
from suites.supervision.protocol import MUTE, OPERATION_COUNT, OPERATION_HOLD

REGISTRATION = 0


class Worker(Service):
    def __init__(self) -> None:
        self._count = 0

    def handle(self, request: ipc.Received) -> Reply:
        if request.message.operation == OPERATION_COUNT:
            self._count += 1
            return Reply(bytes((self._count,)))
        raise KernelError(UNSUPPORTED, "operation is not part of the worker")


def serve(endpoint: int, worker: Worker, supervisor: int) -> bool:
    held = []
    while True:
        request = ipc.receive(endpoint)
        operation = request.message.operation
        if request.reply == 0:
            services.discard_transfer(request)
        elif operation == OPERATION_HOLD:
            held.append(request)
        elif operation == OPERATION_STOP and request.sender == supervisor:
            services.respond(request, Reply())
            return True
        else:
            services.answer(request, worker)


def main() -> bool:
    startup = Startup()
    supervisor, role = decode_supervisor(startup.argument)
    if role == MUTE:
        ipc.receive(ipc.create_endpoint())
        return False
    endpoint = ipc.create_endpoint()
    services.register(startup.handles[REGISTRATION], endpoint, bytes((len(startup.handles),)))
    return serve(endpoint, Worker(), supervisor)
