import pytest

from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.identity.rights import RIGHT_READ, RIGHT_SEND, RIGHTS_ALL
from kernel_protocol.processes.status import ARGUMENT_BYTES, GRANTS, NAME_BYTES, PRIORITY_LEVELS
from kernel_protocol.wire.spawn import (
    PAGE_BYTES,
    REQUEST_BYTES,
    REQUEST_VERSION,
    encode_spawn_request,
    name_is_valid,
)
from native_abi import definitions

FIELDS = definitions("process.h")
PROGRAM = "kernel_services.echo.main"
ARGUMENT = b"first second"
PRIORITY = 2
HEAP_BYTES = 4 * PAGE_BYTES
MEMORY_BYTES = PAGE_BYTES
GRANTED = ((0x1000002, RIGHT_SEND), (0x2000005, RIGHT_SEND | RIGHT_READ))
DEFAULTS = {
    "name": PROGRAM,
    "argument": ARGUMENT,
    "priority": PRIORITY,
    "heap_bytes": HEAP_BYTES,
    "memory_bytes": MEMORY_BYTES,
    "grants": GRANTED,
}


def encoded(**changes) -> bytes:
    return encode_spawn_request(**(DEFAULTS | changes))


def refusal(**changes) -> int:
    with pytest.raises(KernelError) as raised:
        encoded(**changes)
    return raised.value.code


def unsigned(request: bytes, offset: int, width: int) -> int:
    return int.from_bytes(request[offset : offset + width], "little")


def test_every_scalar_is_written_at_its_native_offset() -> None:
    request = encoded()

    assert len(request) == REQUEST_BYTES
    assert unsigned(request, FIELDS["SPAWN_FIELD_VERSION"], 4) == REQUEST_VERSION
    assert unsigned(request, FIELDS["SPAWN_FIELD_PRIORITY"], 4) == PRIORITY
    assert unsigned(request, FIELDS["SPAWN_FIELD_HEAP_BYTES"], 8) == HEAP_BYTES
    assert unsigned(request, FIELDS["SPAWN_FIELD_MEMORY_BYTES"], 8) == MEMORY_BYTES
    assert unsigned(request, FIELDS["SPAWN_FIELD_NAME_LENGTH"], 4) == len(PROGRAM)
    assert unsigned(request, FIELDS["SPAWN_FIELD_ARGUMENT_LENGTH"], 4) == len(ARGUMENT)
    assert unsigned(request, FIELDS["SPAWN_FIELD_GRANT_COUNT"], 4) == len(GRANTED)
    assert unsigned(request, FIELDS["SPAWN_FIELD_RESERVED"], 4) == 0


def test_grants_fill_their_slots_in_order_and_the_rest_stay_zero() -> None:
    request = encoded()
    first, size = FIELDS["SPAWN_FIELD_GRANTS"], FIELDS["SPAWN_GRANT_BYTES"]
    slots = [first + index * size for index in range(GRANTS)]

    for slot, (handle, rights) in zip(slots, GRANTED, strict=False):
        assert unsigned(request, slot + FIELDS["SPAWN_GRANT_HANDLE"], 8) == handle
        assert unsigned(request, slot + FIELDS["SPAWN_GRANT_RIGHTS"], 8) == rights
    assert request[slots[len(GRANTED)] : FIELDS["SPAWN_FIELD_NAME"]] == bytes(
        size * (GRANTS - len(GRANTED))
    )


def test_name_and_argument_are_padded_with_zeros() -> None:
    request = encoded()
    name, argument = FIELDS["SPAWN_FIELD_NAME"], FIELDS["SPAWN_FIELD_ARGUMENT"]

    assert request[name : name + NAME_BYTES] == PROGRAM.encode() + bytes(NAME_BYTES - len(PROGRAM))
    assert request[argument:] == ARGUMENT + bytes(ARGUMENT_BYTES - len(ARGUMENT))


def test_largest_fields_fill_the_request_exactly() -> None:
    argument = bytes(range(ARGUMENT_BYTES))

    request = encoded(name="a" * NAME_BYTES, argument=argument, grants=((7, RIGHTS_ALL),) * GRANTS)

    assert len(request) == REQUEST_BYTES
    assert request[-ARGUMENT_BYTES:] == argument
    assert unsigned(request, FIELDS["SPAWN_FIELD_GRANT_COUNT"], 4) == GRANTS


@pytest.mark.parametrize(
    "name", ["init", "kernel_services.init.main", "suites.ipc.main2", "a" * NAME_BYTES]
)
def test_module_paths_are_valid_program_names(name: str) -> None:
    assert name_is_valid(name)
    assert len(encoded(name=name)) == REQUEST_BYTES


@pytest.mark.parametrize(
    "name",
    ["", "Init", "init.", ".init", "init..main", "init-main", "init main", "a" * (NAME_BYTES + 1)],
)
def test_names_that_are_not_module_paths_are_refused(name: str) -> None:
    assert not name_is_valid(name)
    assert refusal(name=name) == INVALID_ARGUMENT


@pytest.mark.parametrize(
    "changes",
    [
        {"argument": bytes(ARGUMENT_BYTES + 1)},
        {"priority": -1},
        {"priority": PRIORITY_LEVELS},
        {"heap_bytes": PAGE_BYTES + 1},
        {"heap_bytes": -PAGE_BYTES},
        {"memory_bytes": 1},
        {"memory_bytes": -PAGE_BYTES},
        {"grants": ((7, RIGHT_SEND),) * (GRANTS + 1)},
        {"grants": ((0, RIGHT_SEND),)},
        {"grants": ((7, 0),)},
        {"grants": ((7, RIGHTS_ALL + 1),)},
    ],
    ids=lambda changes: next(iter(changes)),
)
def test_requests_outside_the_format_are_refused(changes: dict[str, object]) -> None:
    assert refusal(**changes) == INVALID_ARGUMENT
