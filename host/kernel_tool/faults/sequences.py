import random
from collections.abc import Callable
from dataclasses import dataclass

from kernel_protocol.errors.codes import (
    ALREADY_EXISTS,
    INVALID_ARGUMENT,
    IS_A_DIRECTORY,
    LIMIT_EXCEEDED,
    NO_SPACE,
    NOT_A_DIRECTORY,
    NOT_EMPTY,
    NOT_FOUND,
    KernelError,
    error_name,
)
from kernel_services.filesystem.format.layout import KIND_DIRECTORY, KIND_FILE
from kernel_services.filesystem.transactions.nodes import Node
from kernel_services.filesystem.volume import Volume
from kernel_tool.faults.crash_images import crash_image, random_loss, split
from kernel_tool.faults.recovery import RecordedVolume, recover
from kernel_tool.storage.volumes import create_image

OPERATIONS = 24
CRASHES = 8
VOLUME_BLOCKS = 64
VOLUME = 0x53455155454E
NAMES = (b"a", b"b", b"c", b"d")
MAX_OFFSET = 20000
MAX_WRITE_BYTES = 9000
EXPECTED_REFUSALS = (
    NO_SPACE,
    ALREADY_EXISTS,
    NOT_EMPTY,
    LIMIT_EXCEEDED,
    INVALID_ARGUMENT,
    IS_A_DIRECTORY,
    NOT_A_DIRECTORY,
    NOT_FOUND,
)

type Operation = Callable[[Volume, random.Random], None]


@dataclass(frozen=True, slots=True)
class SequenceResult:
    seed: int
    commits: int
    images: int
    failures: tuple[str, ...]


def run_sequence(seed: int) -> SequenceResult:
    generator = random.Random(seed)
    recorded = RecordedVolume(create_image(VOLUME_BLOCKS, VOLUME))
    try:
        for _ in range(OPERATIONS):
            _apply(generator.choice(WEIGHTED_OPERATIONS), recorded.volume, generator)
    except KernelError as error:
        failure = f"seed {seed}: the volume failed with {error_name(error.code)}: {error.detail}"
        return SequenceResult(seed, len(recorded.history.commits) - 1, 0, (failure,))
    events = recorded.store.events
    failures = []
    for _ in range(CRASHES):
        executed = generator.randint(0, len(events))
        durable, volatile = split(events, executed)
        loss = random_loss(len(volatile), generator)
        image = crash_image(recorded.base, durable, volatile, loss)
        recovery = recover(image, recorded.history, executed)
        if recovery.failure is not None:
            failures.append(
                f"seed {seed} after {executed} events with {loss.describe()}: {recovery.failure}"
            )
    return SequenceResult(seed, len(recorded.history.commits) - 1, CRASHES, tuple(failures))


def _apply(operation: Operation, volume: Volume, generator: random.Random) -> None:
    try:
        operation(volume, generator)
    except KernelError as error:
        if error.code not in EXPECTED_REFUSALS:
            raise


def _nodes(volume: Volume) -> tuple[list[Node], list[Node]]:
    directories: list[Node] = [volume.root()]
    files: list[Node] = []
    visited = 0
    while visited < len(directories):
        directory = directories[visited]
        visited += 1
        for name, kind, _size in volume.listing(directory):
            node = volume.lookup(directory, name)
            (directories if kind == KIND_DIRECTORY else files).append(node)
    return directories, files


def _create_file(volume: Volume, generator: random.Random) -> None:
    directories, _files = _nodes(volume)
    volume.create(generator.choice(directories), generator.choice(NAMES), KIND_FILE)


def _make_directory(volume: Volume, generator: random.Random) -> None:
    directories, _files = _nodes(volume)
    volume.create(generator.choice(directories), generator.choice(NAMES), KIND_DIRECTORY)


def _write(volume: Volume, generator: random.Random) -> None:
    _directories, files = _nodes(volume)
    if files:
        data = generator.randbytes(generator.randrange(1, MAX_WRITE_BYTES))
        volume.write(generator.choice(files), generator.randrange(MAX_OFFSET), data)


def _truncate(volume: Volume, generator: random.Random) -> None:
    _directories, files = _nodes(volume)
    if files:
        volume.truncate(generator.choice(files), generator.randrange(MAX_OFFSET))


def _rename(volume: Volume, generator: random.Random) -> None:
    directories, files = _nodes(volume)
    movable = [*files, *directories[1:]]
    if not movable:
        return
    node = generator.choice(movable)
    if node.parent is not None:
        target = generator.choice(directories)
        volume.rename(node.parent, node.name, target, generator.choice(NAMES))


def _remove(volume: Volume, generator: random.Random) -> None:
    directories, files = _nodes(volume)
    removable = [*files, *directories[1:]]
    if not removable:
        return
    node = generator.choice(removable)
    if node.parent is not None:
        volume.remove(node.parent, node.name)


def _sync(volume: Volume, _generator: random.Random) -> None:
    volume.sync()


WEIGHTED_OPERATIONS: tuple[Operation, ...] = (
    _create_file,
    _create_file,
    _make_directory,
    _write,
    _write,
    _write,
    _truncate,
    _rename,
    _remove,
    _sync,
    _sync,
    _sync,
)
