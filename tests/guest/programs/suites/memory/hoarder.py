from kernel_client import ipc, memory
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import LIMIT_EXCEEDED, KernelError
from kernel_protocol.wire.message import Message

SATURATED_OPERATION = 1
NO_FLAGS = 0


def hoard(block_bytes: int) -> tuple[int, int]:
    held = 0
    while True:
        try:
            memory.create_buffer(block_bytes)
        except KernelError as error:
            return held, error.code
        held += 1


def main() -> bool:
    startup = Startup()
    block_bytes, expected = (int(field) for field in str(startup.argument, "ascii").split(" "))
    held, refusal = hoard(block_bytes)
    if held != expected or refusal != LIMIT_EXCEEDED:
        print(f"hoarder: held={held} expected={expected} refusal={refusal}")
        return False
    if startup.handles:
        ipc.send(startup.handles[0], Message(SATURATED_OPERATION, NO_FLAGS, held, b""))
        ipc.receive(ipc.create_endpoint())
    return True
