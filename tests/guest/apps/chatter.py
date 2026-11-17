from kernel_apps import runtime
from kernel_protocol.services.files import OPEN_CREATE, OPEN_READ, OPEN_TRUNCATE, OPEN_WRITE

RECORD = b"chatter record\n" * 64
REPLACE = OPEN_WRITE | OPEN_CREATE | OPEN_TRUNCATE


def main() -> bool:
    application = runtime.current()
    namespace = application.files
    if namespace is None or len(application.arguments) != 2:
        print("chatter: usage=chatter.py <path>")
        return False
    path = bytes(application.arguments[1], "utf-8")
    print("chatter: started")
    while True:
        target = namespace.open(path, REPLACE)
        target.write(0, RECORD)
        target.close()
        source = namespace.open(path, OPEN_READ)
        source.read(0, source.size)
        source.close()
