from kernel_client import ipc


def main() -> bool:
    ipc.receive(ipc.create_endpoint())
    return False
