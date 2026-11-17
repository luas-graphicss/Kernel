from kernel_client import ipc

CHUNK_BYTES = 65536
CHUNKS = 20


def main() -> bool:
    held = [bytearray(CHUNK_BYTES) for _ in range(CHUNKS)]
    print(f"ballast: held={len(held) * CHUNK_BYTES}")
    ipc.receive(ipc.create_endpoint())
    return False
