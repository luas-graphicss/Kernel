import pytest

from kernel_services.filesystem.format.layout import KIND_FILE
from kernel_tool.faults.matrix import BEFORE_ANY_EVENT, CrashPoint, run_matrix
from kernel_tool.faults.recovery import RecordedVolume, recover
from kernel_tool.faults.sequences import CRASHES, run_sequence
from kernel_tool.faults.transactions import TRANSACTIONS
from kernel_tool.storage.volumes import create_image

VOLUME_BLOCKS = 64
VOLUME = 0x54455354
FLUSH = "flush"
SUPERBLOCK = "superblock of generation "
FILE = b"kept.bin"
CHECKED_SEEDS = range(1, 13)

type Matrix = dict[str, list[CrashPoint]]


@pytest.fixture(scope="module")
def matrix() -> Matrix:
    grouped: Matrix = {}
    for point in run_matrix():
        grouped.setdefault(point.transaction, []).append(point)
    return grouped


def committed(content: bytes) -> RecordedVolume:
    recorded = RecordedVolume(create_image(VOLUME_BLOCKS, VOLUME))
    volume = recorded.volume
    volume.write(volume.create(volume.root(), FILE, KIND_FILE), 0, content)
    volume.sync()
    return recorded


def published_at(points: list[CrashPoint]) -> int:
    return next(index for index, point in enumerate(points) if point.after.startswith(SUPERBLOCK))


def test_every_minimal_transaction_is_crashed_after_each_device_event(matrix: Matrix) -> None:
    assert list(matrix) == [name for name, _transaction in TRANSACTIONS]
    for points in matrix.values():
        assert [point.executed for point in points] == list(range(len(points)))
        assert points[0].after == BEFORE_ANY_EVENT


def test_no_crash_point_fails_recovery(matrix: Matrix) -> None:
    failed = [point for points in matrix.values() for point in points if point.failures]

    assert failed == []


def test_a_transaction_flushes_its_tree_before_and_after_its_only_superblock(
    matrix: Matrix,
) -> None:
    for points in matrix.values():
        events = [point.after for point in points[1:]]
        published = [index for index, event in enumerate(events) if event.startswith(SUPERBLOCK)]

        assert len(published) == 1
        assert events[published[0] - 1] == FLUSH
        assert events[published[0] + 1 :] == [FLUSH]


def test_a_change_is_visible_only_after_its_superblock_was_sent(matrix: Matrix) -> None:
    for points in matrix.values():
        published = published_at(points)

        assert all(point.recovered_after == 0 for point in points[:published])
        assert points[published].recovered_before > 0
        assert points[published].recovered_after > 0
        assert (points[-1].images, points[-1].recovered_after) == (1, 1)


def test_recovery_accepts_the_image_left_by_a_finished_commit() -> None:
    recorded = committed(b"kept")

    recovery = recover(bytes(recorded.store.content), recorded.history, len(recorded.store.events))

    assert recovery.failure is None
    assert recovery.generation == recorded.volume.generation()


def test_recovery_reports_a_confirmed_commit_that_the_device_lost() -> None:
    recorded = committed(b"kept")

    recovery = recover(recorded.base, recorded.history, len(recorded.store.events))

    assert recovery.failure is not None
    assert "was confirmed but generation" in recovery.failure


def test_recovery_allows_a_commit_that_was_never_confirmed_to_be_missing() -> None:
    recorded = committed(b"kept")

    recovery = recover(recorded.base, recorded.history, 0)

    assert recovery.failure is None
    assert recovery.generation == recorded.volume.generation() - 1


def test_recovery_reports_content_that_differs_from_what_was_committed() -> None:
    recorded = committed(b"kept")
    other = committed(b"lost")

    recovery = recover(bytes(other.store.content), recorded.history, len(recorded.store.events))

    assert recovery.failure is not None
    assert "instead of" in recovery.failure


def test_recovery_reports_an_image_that_does_not_mount() -> None:
    recorded = committed(b"kept")

    recovery = recover(bytes(len(recorded.base)), recorded.history, 0)

    assert recovery.generation is None
    assert recovery.failure is not None
    assert "does not mount" in recovery.failure


def test_a_seed_always_generates_the_same_sequence() -> None:
    assert run_sequence(11) == run_sequence(11)


def test_generated_sequences_recover_every_crash_they_inject() -> None:
    results = [run_sequence(seed) for seed in CHECKED_SEEDS]

    assert [result.failures for result in results] == [()] * len(results)
    assert all(result.images == CRASHES for result in results)
    assert len({result.commits for result in results}) > 1
