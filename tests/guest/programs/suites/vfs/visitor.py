from kernel_client import files, processes, services
from kernel_protocol.errors.codes import ACCESS_DENIED, INVALID_HANDLE
from kernel_protocol.services.files import (
    OPEN_CREATE,
    OPEN_WRITE,
    OPERATION_READ,
    OPERATION_STAT,
    encode_extent,
    encode_request,
)
from suites.support.expectations import error_code
from suites.support.platform import load, store
from suites.vfs.records import RECORD_BYTES, RECORDS, WRITERS, record_of

SERVICE = 0
NAMESPACE = 1
INSIDE_NAME = b"inside.txt"
INSIDE_NOTE = b"written by the confined process"
SHARED_NAME = b"shared.bin"
PROBED_BYTES = 16


def number(text: bytes) -> int:
    return int(str(text, "ascii"))


def stay_confined(startup: processes.Startup, _words: list[bytes]) -> bool:
    namespace = files.Namespace(startup.handles[SERVICE], startup.handles[NAMESPACE])
    store(namespace, INSIDE_NAME, INSIDE_NOTE)
    confined = (
        load(namespace, INSIDE_NAME) == INSIDE_NOTE
        and error_code(namespace.stat, b"..") == ACCESS_DENIED
        and error_code(load, namespace, b"../secret.txt") == ACCESS_DENIED
        and error_code(store, namespace, b"shown.txt/../../secret.txt", b"x") == ACCESS_DENIED
    )
    namespace.leave()
    return confined


def use_what_is_not_mine(startup: processes.Startup, words: list[bytes]) -> bool:
    service = startup.handles[SERVICE]
    instance = number(words[1])
    reading = encode_request(instance, number(words[3]), encode_extent(0, PROBED_BYTES))
    asking = encode_request(instance, number(words[2]), b"tmp")
    return (
        error_code(services.call, service, OPERATION_READ, reading) == INVALID_HANDLE
        and error_code(services.call, service, OPERATION_STAT, asking) == INVALID_HANDLE
    )


def write_records(startup: processes.Startup, words: list[bytes]) -> bool:
    slot = number(words[1])
    namespace = files.Namespace(startup.handles[SERVICE], startup.handles[NAMESPACE])
    shared = namespace.open(SHARED_NAME, OPEN_WRITE | OPEN_CREATE)
    own = namespace.open(bytes(f"writer-{slot}", "ascii"), OPEN_WRITE | OPEN_CREATE)
    complete = True
    for record in range(RECORDS):
        content = record_of(slot, record)
        offset = (record * WRITERS + slot) * RECORD_BYTES
        complete = shared.write(offset, content) == RECORD_BYTES and complete
        complete = own.write(record * RECORD_BYTES, content) == RECORD_BYTES and complete
        processes.yield_now()
    own.close()
    shared.close()
    namespace.leave()
    return complete


ROLES = {
    b"confined": stay_confined,
    b"stranger": use_what_is_not_mine,
    b"writer": write_records,
}


def main() -> bool:
    startup = processes.Startup()
    words = startup.argument.split(b" ")
    return ROLES[words[0]](startup, words)
