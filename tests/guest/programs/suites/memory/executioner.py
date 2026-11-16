from kernel_client import ipc, processes
from kernel_protocol.wire.message import Message

ENDPOINT_OPERATION = 1
NO_FLAGS = 0


def main() -> bool:
    endpoint = ipc.create_endpoint()
    registrations = processes.Startup().handles[0]
    ipc.send(registrations, Message(ENDPOINT_OPERATION, NO_FLAGS, 0, b""), endpoint)
    request = ipc.receive(endpoint)
    processes.kill(request.transferred)
    ipc.answer(request, b"")
    return True
