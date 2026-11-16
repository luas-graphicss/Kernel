from kernel_apps import runtime
from kernel_protocol.services.files import OPEN_READ

CHUNK_BYTES = 1024
LINE_BREAK = 0x0A
SEPARATORS = (0x20, 0x09, 0x0A, 0x0D)


def count(path: str) -> tuple[int, int, int]:
    namespace = runtime.current().files
    if namespace is None:
        raise ValueError("the application was started without files")
    opened = namespace.open(bytes(path, "utf-8"), OPEN_READ)
    lines = 0
    words = 0
    size = 0
    in_word = False
    try:
        while size < opened.size:
            chunk = opened.read(size, CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            for value in chunk:
                if value == LINE_BREAK:
                    lines += 1
                if value in SEPARATORS:
                    in_word = False
                elif not in_word:
                    in_word = True
                    words += 1
    finally:
        opened.close()
    return lines, words, size


def main() -> bool:
    arguments = runtime.current().arguments
    if len(arguments) != 2:
        print("wordcount: usage=wordcount.py <path>")
        return False
    lines, words, size = count(arguments[1])
    print(f"wordcount: path={arguments[1]} lines={lines} words={words} bytes={size}")
    return True
