import struct
from collections.abc import Iterator
from dataclasses import dataclass, replace

from kernel_tool.outcome import CheckError

MAGIC = 0xD00DFEED
HEADER = struct.Struct(">10I")
TOKEN = struct.Struct(">I")
PROPERTY = struct.Struct(">II")
RESERVATION = struct.Struct(">QQ")
BEGIN_NODE = 1
END_NODE = 2
PROPERTY_TOKEN = 3
NOP = 4
END = 9
ALIGNMENT = 4
ROOT_PATH = "/"


@dataclass(frozen=True, slots=True)
class DeviceTree:
    version: int
    last_compatible_version: int
    boot_cpu: int
    reservations: bytes
    structure: bytes
    strings: bytes


@dataclass(frozen=True, slots=True)
class Token:
    kind: int
    start: int
    end: int
    path: str


def parse(blob: bytes) -> DeviceTree:
    try:
        return _parse(blob)
    except (struct.error, ValueError, UnicodeDecodeError) as error:
        raise CheckError(f"malformed device tree: {error}") from error


def serialize(tree: DeviceTree) -> bytes:
    reservations_offset = HEADER.size
    structure_offset = reservations_offset + len(tree.reservations)
    strings_offset = structure_offset + len(tree.structure)
    header = HEADER.pack(
        MAGIC,
        strings_offset + len(tree.strings),
        structure_offset,
        strings_offset,
        reservations_offset,
        tree.version,
        tree.last_compatible_version,
        tree.boot_cpu,
        len(tree.strings),
        len(tree.structure),
    )
    return header + tree.reservations + tree.structure + tree.strings


def node_paths(tree: DeviceTree) -> list[str]:
    return [token.path for token in _tokens(tree.structure) if token.kind == BEGIN_NODE]


def without_node(tree: DeviceTree, path: str) -> DeviceTree:
    kept = bytearray()
    removed = False
    for token in _tokens(tree.structure):
        if token.path == path or token.path.startswith(f"{path}/"):
            removed = True
            continue
        kept += tree.structure[token.start : token.end]
    if not removed or path == ROOT_PATH:
        raise CheckError(f"device tree has no removable node {path}")
    return replace(tree, structure=bytes(kept))


def with_property(tree: DeviceTree, path: str, name: str, value: bytes) -> DeviceTree:
    padding = bytes(-len(value) % ALIGNMENT)
    encoded = (
        TOKEN.pack(PROPERTY_TOKEN) + PROPERTY.pack(len(value), len(tree.strings)) + value + padding
    )
    for token in _tokens(tree.structure):
        if token.kind == BEGIN_NODE and token.path == path:
            return replace(
                tree,
                structure=tree.structure[: token.end] + encoded + tree.structure[token.end :],
                strings=tree.strings + name.encode("ascii") + b"\0",
            )
    raise CheckError(f"device tree has no node {path}")


def _parse(blob: bytes) -> DeviceTree:
    (
        magic,
        total_bytes,
        structure_offset,
        strings_offset,
        reservations_offset,
        version,
        last_compatible_version,
        boot_cpu,
        strings_bytes,
        structure_bytes,
    ) = HEADER.unpack_from(blob)
    if magic != MAGIC:
        raise ValueError(f"magic is {magic:#x}")
    if total_bytes > len(blob):
        raise ValueError(f"header declares {total_bytes} bytes but the blob has {len(blob)}")
    tree = DeviceTree(
        version=version,
        last_compatible_version=last_compatible_version,
        boot_cpu=boot_cpu,
        reservations=_reservations(blob[:total_bytes], reservations_offset),
        structure=_block(blob, structure_offset, structure_bytes, total_bytes),
        strings=_block(blob, strings_offset, strings_bytes, total_bytes),
    )
    for _ in _tokens(tree.structure):
        pass
    return tree


def _block(blob: bytes, offset: int, length: int, total_bytes: int) -> bytes:
    if offset + length > total_bytes:
        raise ValueError(f"block at {offset} with {length} bytes leaves the blob")
    return blob[offset : offset + length]


def _reservations(blob: bytes, offset: int) -> bytes:
    end = offset
    while True:
        address, length = RESERVATION.unpack_from(blob, end)
        end += RESERVATION.size
        if address == 0 and length == 0:
            return blob[offset:end]


def _aligned(offset: int) -> int:
    return offset + (-offset % ALIGNMENT)


def _tokens(structure: bytes) -> Iterator[Token]:
    names: list[str] = []
    offset = 0
    while True:
        start = offset
        (kind,) = TOKEN.unpack_from(structure, offset)
        offset += TOKEN.size
        if kind == BEGIN_NODE:
            terminator = structure.index(b"\0", offset)
            names.append(structure[offset:terminator].decode("ascii"))
            offset = _aligned(terminator + 1)
        elif kind == PROPERTY_TOKEN:
            length, _name_offset = PROPERTY.unpack_from(structure, offset)
            offset = _aligned(offset + PROPERTY.size + length)
        elif kind not in (END_NODE, NOP, END):
            raise ValueError(f"unknown structure token {kind}")
        if offset > len(structure):
            raise ValueError("a structure token leaves the structure block")
        yield Token(kind=kind, start=start, end=offset, path="/".join(names) or ROOT_PATH)
        if kind == END_NODE:
            if not names:
                raise ValueError("a node ends before it begins")
            names.pop()
        if kind == END:
            if names:
                raise ValueError("the structure ends inside a node")
            return
