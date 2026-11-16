import random

from kernel_services.filesystem.format.layout import BLOCK_BYTES
from kernel_tool.faults.crash_images import (
    EXHAUSTIVE_WRITES,
    TORN_BYTES,
    Loss,
    crash_image,
    losses,
    random_loss,
    split,
)
from kernel_tool.faults.device_log import DeviceFlush, DeviceWrite

BLOCKS = 4
BASE = bytes(BLOCKS * BLOCK_BYTES)
MANY_WRITES = EXHAUSTIVE_WRITES + 6
DRAWN_LOSSES = 200


def filled(value: int) -> bytes:
    return bytes([value]) * BLOCK_BYTES


def write(block: int, value: int) -> DeviceWrite:
    return DeviceWrite(block, filled(value))


def block_of(image: bytes, block: int) -> bytes:
    return image[block * BLOCK_BYTES : (block + 1) * BLOCK_BYTES]


def test_writes_become_durable_only_at_the_next_flush() -> None:
    first, second, third, fourth = write(0, 1), write(1, 2), write(2, 3), write(3, 4)
    events = [first, second, DeviceFlush(), third, DeviceFlush(), fourth]

    assert split(events, 0) == ([], [])
    assert split(events, 2) == ([], [first, second])
    assert split(events, 3) == ([first, second], [])
    assert split(events, 4) == ([first, second], [third])
    assert split(events, 6) == ([first, second, third], [fourth])


def test_few_volatile_writes_are_lost_in_every_combination() -> None:
    for volatile in range(EXHAUSTIVE_WRITES + 1):
        found = losses(volatile)
        whole = {loss.kept for loss in found if loss.torn is None}

        assert len(whole) == 2**volatile
        assert len(found) == len(set(found))
        assert {loss.torn for loss in found if loss.torn is not None} == set(range(volatile))


def test_many_volatile_writes_are_lost_in_a_bounded_number_of_patterns() -> None:
    everything = frozenset(range(MANY_WRITES))
    found = losses(MANY_WRITES)
    whole = {loss.kept for loss in found if loss.torn is None}

    assert all(frozenset(range(size)) in whole for size in range(MANY_WRITES + 1))
    assert all(frozenset({index}) in whole for index in everything)
    assert all(everything - {index} in whole for index in everything)
    assert {loss.torn for loss in found if loss.torn is not None} == set(everything)
    assert len(found) <= 6 * MANY_WRITES


def test_a_torn_write_is_never_also_kept() -> None:
    for volatile in (1, EXHAUSTIVE_WRITES, MANY_WRITES):
        assert all(loss.torn not in loss.kept for loss in losses(volatile))


def test_an_image_holds_durable_writes_kept_writes_and_half_of_a_torn_one() -> None:
    volatile = [write(1, 2), write(2, 3), write(3, 4)]

    image = crash_image(BASE, [write(0, 1)], volatile, Loss(frozenset({0}), torn=2))

    assert len(image) == len(BASE)
    assert block_of(image, 0) == filled(1)
    assert block_of(image, 1) == filled(2)
    assert block_of(image, 2) == bytes(BLOCK_BYTES)
    assert block_of(image, 3) == bytes([4]) * TORN_BYTES + bytes(BLOCK_BYTES - TORN_BYTES)


def test_the_last_write_that_survived_decides_the_block() -> None:
    durable = [write(0, 1), write(0, 2)]

    assert block_of(crash_image(BASE, durable, [write(0, 3)], Loss(frozenset({0}))), 0) == filled(3)
    assert block_of(crash_image(BASE, durable, [write(0, 3)], Loss(frozenset())), 0) == filled(2)


def test_random_losses_are_reproducible_and_stay_inside_the_volatile_writes() -> None:
    first_generator = random.Random(9)
    second_generator = random.Random(9)
    first = [random_loss(5, first_generator) for _ in range(DRAWN_LOSSES)]
    second = [random_loss(5, second_generator) for _ in range(DRAWN_LOSSES)]

    assert first == second
    assert all(loss.kept <= frozenset(range(5)) for loss in first)
    assert all(loss.torn is None or 0 <= loss.torn < 5 for loss in first)
    assert any(loss.torn is None for loss in first)
    assert any(loss.torn is not None for loss in first)
    assert random_loss(0, first_generator) == Loss(frozenset())


def test_a_loss_describes_what_survived() -> None:
    assert Loss(frozenset()).describe() == "kept=none"
    assert Loss(frozenset({2, 0}), 1).describe() == "kept=0,2 torn=1"
