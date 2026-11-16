from dataclasses import asdict, dataclass
from enum import StrEnum

from kernel_protocol.errors.codes import UNSUPPORTED, KernelError
from kernel_services.filesystem.creation import create_volume
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    KIND_DIRECTORY,
    MAX_BLOCKS,
    MIN_BLOCKS,
    SUPERBLOCK_SLOTS,
)
from kernel_services.filesystem.recovery.digest import tree_digest
from kernel_services.filesystem.recovery.mount import Slot, mount, read_slot
from kernel_services.filesystem.transactions.nodes import Node
from kernel_services.filesystem.volume import Volume
from kernel_tool.outcome import CheckError
from kernel_tool.storage.image_store import ImageStore

SEPARATOR = "/"


class Verdict(StrEnum):
    MOUNTABLE = "mountable"
    READ_ONLY = "read-only"
    CORRUPTED = "corrupted"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class SlotReport:
    number: int
    valid: bool
    generation: int | None
    problem: str


@dataclass(frozen=True, slots=True)
class VolumeReport:
    verdict: Verdict
    reason: str
    generation: int | None
    total_blocks: int | None
    used_blocks: int | None
    directories: int | None
    files: int | None
    file_bytes: int | None
    digest: str | None
    slots: tuple[SlotReport, ...]

    def to_document(self) -> dict[str, object]:
        return asdict(self) | {"verdict": self.verdict.value}


@dataclass(frozen=True, slots=True)
class TreeEntry:
    path: str
    kind: str
    size: int


def create_image(blocks: int, volume: int) -> bytes:
    if blocks < MIN_BLOCKS or blocks > MAX_BLOCKS:
        raise CheckError(f"a volume holds between {MIN_BLOCKS} and {MAX_BLOCKS} blocks")
    store = ImageStore(bytes(blocks * BLOCK_BYTES))
    create_volume(store, volume)
    return bytes(store.content)


def verify_image(content: bytes, *, deep: bool = True) -> VolumeReport:
    store = ImageStore(content)
    try:
        mounted = mount(store, deep)
    except KernelError as error:
        verdict = Verdict.UNSUPPORTED if error.code == UNSUPPORTED else Verdict.CORRUPTED
        return _refused(verdict, error.detail, store)
    survey = mounted.survey
    return VolumeReport(
        verdict=Verdict.READ_ONLY if mounted.read_only else Verdict.MOUNTABLE,
        reason=mounted.reason,
        generation=mounted.superblock.generation,
        total_blocks=mounted.superblock.total_blocks,
        used_blocks=survey.used_blocks,
        directories=survey.directories,
        files=survey.files,
        file_bytes=survey.file_bytes,
        digest=f"{tree_digest(Volume(store, mounted)):08x}",
        slots=tuple(_slot_report(slot) for slot in mounted.slots),
    )


def list_tree(content: bytes) -> tuple[TreeEntry, ...]:
    store = ImageStore(content)
    volume = Volume(store, mount(store, True))
    entries = []
    pending: list[tuple[str, Node]] = [("", volume.root())]
    while pending:
        prefix, directory = pending.pop()
        for name, kind, size in volume.listing(directory):
            path = prefix + SEPARATOR + name.decode("utf-8", errors="backslashreplace")
            is_directory = kind == KIND_DIRECTORY
            entries.append(TreeEntry(path, "directory" if is_directory else "file", size))
            if is_directory:
                pending.append((path, volume.lookup(directory, name)))
    return tuple(sorted(entries, key=lambda entry: entry.path))


def _refused(verdict: Verdict, reason: str, store: ImageStore) -> VolumeReport:
    slots: tuple[SlotReport, ...] = ()
    if store.blocks >= SUPERBLOCK_SLOTS:
        slots = tuple(_slot_report(read_slot(store, number)) for number in range(SUPERBLOCK_SLOTS))
    return VolumeReport(verdict, reason, None, None, None, None, None, None, None, slots)


def _slot_report(slot: Slot) -> SlotReport:
    superblock = slot.superblock
    return SlotReport(
        number=slot.number,
        valid=superblock is not None,
        generation=superblock.generation if superblock is not None else None,
        problem=slot.problem,
    )
