import pytest

from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    LIMIT_EXCEEDED,
    KernelError,
)
from kernel_protocol.identity.handles import (
    GENERATION_BITS,
    INDEX_BITS,
    HandleTable,
    handle_generation,
    handle_index,
    pack_handle,
)


def error_code(operation, *arguments: int) -> int:
    with pytest.raises(KernelError) as raised:
        operation(*arguments)
    return raised.value.code


def test_first_handle_uses_slot_zero_and_generation_one() -> None:
    table = HandleTable(4, GENERATION_BITS)

    handle = table.allocate()

    assert handle_index(handle) == 0
    assert handle_generation(handle) == 1
    assert handle == 1 << INDEX_BITS
    assert table.resolve(handle) == 0


def test_released_handle_stays_invalid_after_the_slot_is_reused() -> None:
    table = HandleTable(4, GENERATION_BITS)
    stale = table.allocate()
    table.release(stale)

    reused = table.allocate()

    assert handle_index(reused) == handle_index(stale)
    assert handle_generation(reused) == handle_generation(stale) + 1
    assert error_code(table.resolve, stale) == INVALID_HANDLE
    assert error_code(table.release, stale) == INVALID_HANDLE
    assert table.resolve(reused) == 0


def test_most_recently_released_slot_is_reused_first() -> None:
    table = HandleTable(4, GENERATION_BITS)
    handles = [table.allocate() for _ in range(3)]
    table.release(handles[0])
    table.release(handles[2])

    assert handle_index(table.allocate()) == 2
    assert handle_index(table.allocate()) == 0


def test_exhausted_generation_retires_the_slot() -> None:
    table = HandleTable(1, 2)
    for _ in range(3):
        table.release(table.allocate())

    assert table.retired == 1
    assert table.free_slots() == 0
    assert error_code(table.allocate) == LIMIT_EXCEEDED


def test_full_table_refuses_allocation_without_side_effects() -> None:
    table = HandleTable(2, GENERATION_BITS)
    handles = [table.allocate(), table.allocate()]

    assert error_code(table.allocate) == LIMIT_EXCEEDED
    assert table.live == 2
    assert [table.resolve(handle) for handle in handles] == [0, 1]


@pytest.mark.parametrize(
    "handle",
    [
        0,
        -1,
        pack_handle(9, 1),
        pack_handle(0, 2),
        pack_handle(0, 1) | 1 << (INDEX_BITS + GENERATION_BITS),
    ],
    ids=["zero", "negative", "index-outside-table", "wrong-generation", "reserved-bits"],
)
def test_malformed_handles_do_not_resolve(handle: int) -> None:
    table = HandleTable(4, GENERATION_BITS)
    table.allocate()

    assert error_code(table.resolve, handle) == INVALID_HANDLE


@pytest.mark.parametrize(("capacity", "generation_bits"), [(0, 8), (1 << 25, 8), (4, 0), (4, 33)])
def test_table_rejects_parameters_outside_the_handle_format(
    capacity: int, generation_bits: int
) -> None:
    assert error_code(HandleTable, capacity, generation_bits) == INVALID_ARGUMENT
