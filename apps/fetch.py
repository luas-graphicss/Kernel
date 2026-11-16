from kernel_apps import runtime
from kernel_protocol.services.files import OPEN_CREATE, OPEN_TRUNCATE, OPEN_WRITE
from kernel_services.network.ipv4.address import parse_address

CHUNK_BYTES = 2048
TIMEOUT_NANOSECONDS = 10000000000


def main() -> bool:
    application = runtime.current()
    arguments = application.arguments
    network = application.network
    namespace = application.files
    if len(arguments) != 4 or network is None or namespace is None:
        print("fetch: usage=fetch.py <address> <port> <path>")
        return False
    stream = network.stream()
    target = namespace.open(bytes(arguments[3], "utf-8"), OPEN_WRITE | OPEN_CREATE | OPEN_TRUNCATE)
    received = 0
    try:
        stream.connect(parse_address(arguments[1]), int(arguments[2]), TIMEOUT_NANOSECONDS)
        while True:
            data = stream.receive(CHUNK_BYTES, TIMEOUT_NANOSECONDS)
            if not data:
                break
            target.write(received, data)
            received += len(data)
        target.sync()
    finally:
        target.close()
        stream.close()
    print(f"fetch: path={arguments[3]} bytes={received}")
    return True
