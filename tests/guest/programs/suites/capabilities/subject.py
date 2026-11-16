import _probe

import _process
from kernel_client import capabilities, ipc
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import BAD_ADDRESS, INVALID_HANDLE, OK, KernelError
from kernel_protocol.identity.rights import RIGHT_READ, RIGHT_SEND
from kernel_protocol.syscalls.numbers import DEBUG_WRITE
from kernel_protocol.wire.message import Message
from suites.support import raw
from suites.support.expectations import error_code

SECRET = b"lent-out"
SUBJECT_OPERATION = 1
NO_FLAGS = 0
SLOT_INDEX_BITS = 24
PROBED_SLOTS = 16
PROBED_GENERATIONS = (1, 2)
WORD_BYTES = 8


def note() -> Message:
    return Message(SUBJECT_OPERATION, NO_FLAGS, 0, b"")


def candidate_handles() -> list[int]:
    return [
        (generation << SLOT_INDEX_BITS) | slot
        for generation in PROBED_GENERATIONS
        for slot in range(PROBED_SLOTS)
    ]


def grants_system_authority(handle: int) -> bool:
    return not isinstance(_process.counters(handle), int)


def send_until_revoked(startup: Startup) -> bool:
    granted = startup.handles[0]
    capabilities.derive(granted, RIGHT_SEND)
    sent = 0
    while True:
        try:
            ipc.send(granted, note())
        except KernelError as error:
            return sent > 0 and error.code == INVALID_HANDLE
        sent += 1


def hold_nothing(startup: Startup) -> bool:
    if startup.handles:
        return False
    return all(
        error_code(capabilities.inspect, handle) == INVALID_HANDLE for handle in candidate_handles()
    )


def try_forged_handles(startup: Startup) -> bool:
    endpoint = ipc.create_endpoint()
    ipc.send(startup.handles[0], note(), endpoint)
    received = ipc.receive(endpoint)
    claimed = [
        raw.read_word(received.message.payload, offset)
        for offset in range(0, len(received.message.payload), WORD_BYTES)
    ]
    if received.transferred != 0:
        return False
    return not any(grants_system_authority(handle) for handle in claimed + candidate_handles())


def lose_a_mapping(startup: Startup) -> bool:
    reports, buffer = startup.handles
    status, address, _length = raw.map_buffer(buffer, RIGHT_READ)
    if status != OK or _probe.load(address) != int.from_bytes(SECRET, "little"):
        return False
    resume = ipc.create_endpoint()
    ipc.send(reports, note(), resume)
    ipc.receive(resume)
    return (
        raw.call(DEBUG_WRITE, address, WORD_BYTES) == -BAD_ADDRESS
        and error_code(capabilities.inspect, buffer) == INVALID_HANDLE
    )


ROLES = {
    b"sender": send_until_revoked,
    b"bare": hold_nothing,
    b"forger": try_forged_handles,
    b"borrower": lose_a_mapping,
}


def main() -> bool:
    startup = Startup()
    return ROLES[startup.argument](startup)
