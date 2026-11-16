from kernel_client import ipc
from kernel_client.processes import Startup
from kernel_protocol.wire.message import Message
from kernel_services.echo.protocol import OPERATION_ECHO, OPERATION_REGISTER, OPERATION_STOP

NO_FLAGS = 0
REGISTRATION_CORRELATION = 1


def main() -> bool:
    registration = Startup().handles[0]
    endpoint = ipc.create_endpoint()
    ipc.send(
        registration,
        Message(OPERATION_REGISTER, NO_FLAGS, REGISTRATION_CORRELATION, b""),
        endpoint,
    )
    while True:
        request = ipc.receive(endpoint)
        if request.reply == 0:
            continue
        if request.message.operation == OPERATION_ECHO:
            ipc.answer(request, request.message.payload)
        elif request.message.operation == OPERATION_STOP:
            ipc.answer(request, b"")
            return True
        else:
            ipc.answer(request, b"")
