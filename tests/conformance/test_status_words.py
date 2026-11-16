from kernel_protocol.identity.rights import (
    INSPECT_DEPTH_SHIFT,
    INSPECT_RIGHTS_SHIFT,
    OBJECT_BUFFER,
    OBJECT_ENDPOINT,
    RIGHT_MAP,
    RIGHT_READ,
    RIGHT_SEND,
    RIGHTS_ALL,
    unpack_inspection,
)
from kernel_protocol.processes.status import (
    REASON_NAMES,
    WAIT_REASON_EXIT,
    WAIT_REASON_FAULT,
    WAIT_REASON_KILLED,
    WAIT_REASON_SHIFT,
    WAIT_VALUE_MASK,
    unpack_wait_status,
)


def test_wait_status_splits_into_reason_and_value() -> None:
    faulted = (WAIT_REASON_FAULT << WAIT_REASON_SHIFT) | 13
    exited = (WAIT_REASON_EXIT << WAIT_REASON_SHIFT) | WAIT_VALUE_MASK

    assert unpack_wait_status(faulted) == (WAIT_REASON_FAULT, 13)
    assert unpack_wait_status(exited) == (WAIT_REASON_EXIT, WAIT_VALUE_MASK)
    assert unpack_wait_status(WAIT_REASON_KILLED << WAIT_REASON_SHIFT) == (WAIT_REASON_KILLED, 0)


def test_every_wait_reason_has_a_name() -> None:
    assert REASON_NAMES[WAIT_REASON_EXIT] == "exit"
    assert REASON_NAMES[WAIT_REASON_FAULT] == "fault"
    assert REASON_NAMES[WAIT_REASON_KILLED] == "killed"


def test_inspection_splits_into_kind_rights_and_depth() -> None:
    endpoint = OBJECT_ENDPOINT | (RIGHT_SEND | RIGHT_READ) << INSPECT_RIGHTS_SHIFT
    buffer = OBJECT_BUFFER | RIGHTS_ALL << INSPECT_RIGHTS_SHIFT | 5 << INSPECT_DEPTH_SHIFT

    assert unpack_inspection(endpoint) == (OBJECT_ENDPOINT, RIGHT_SEND | RIGHT_READ, 0)
    assert unpack_inspection(buffer) == (OBJECT_BUFFER, RIGHTS_ALL, 5)
    assert unpack_inspection(OBJECT_BUFFER | RIGHT_MAP << INSPECT_RIGHTS_SHIFT)[1] == RIGHT_MAP
