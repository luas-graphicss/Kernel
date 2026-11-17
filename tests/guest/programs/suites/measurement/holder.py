from kernel_client import ipc

HELD_BYTES = 0x20000


def main() -> bool:
    held = bytearray(HELD_BYTES)
    held[0] = 1
    ipc.receive(ipc.create_endpoint())
    return False
