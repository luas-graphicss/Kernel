import struct

import pytest

from kernel_tool.images.device_tree import (
    BEGIN_NODE,
    END,
    END_NODE,
    HEADER,
    MAGIC,
    PROPERTY,
    PROPERTY_TOKEN,
    TOKEN,
    node_paths,
    parse,
    serialize,
    with_property,
    without_node,
)
from kernel_tool.outcome import CheckError

STRINGS = b"reg\0bootargs\0"
REG_NAME = 0
BOOTARGS_NAME = 4


def begin(name: str) -> bytes:
    encoded = name.encode("ascii") + b"\0"
    return TOKEN.pack(BEGIN_NODE) + encoded + bytes(-len(encoded) % 4)


def prop(name_offset: int, value: bytes) -> bytes:
    return (
        TOKEN.pack(PROPERTY_TOKEN)
        + PROPERTY.pack(len(value), name_offset)
        + value
        + bytes(-len(value) % 4)
    )


def end_node() -> bytes:
    return TOKEN.pack(END_NODE)


def reference_blob() -> bytes:
    structure = (
        begin("")
        + begin("chosen")
        + prop(BOOTARGS_NAME, b"quiet\0")
        + end_node()
        + begin("memory@80000000")
        + prop(REG_NAME, struct.pack(">QQ", 0x80000000, 0x10000000))
        + begin("bank")
        + end_node()
        + end_node()
        + begin("soc")
        + end_node()
        + end_node()
        + TOKEN.pack(END)
    )
    reservations = struct.pack(">QQQQ", 0x80000000, 0x40000, 0, 0)
    structure_offset = HEADER.size + len(reservations)
    strings_offset = structure_offset + len(structure)
    header = HEADER.pack(
        MAGIC,
        strings_offset + len(STRINGS),
        structure_offset,
        strings_offset,
        HEADER.size,
        17,
        16,
        0,
        len(STRINGS),
        len(structure),
    )
    return header + reservations + structure + STRINGS


def test_serializing_a_parsed_tree_returns_the_same_blob() -> None:
    blob = reference_blob()

    assert serialize(parse(blob)) == blob


def test_nodes_are_listed_by_path() -> None:
    assert node_paths(parse(reference_blob())) == [
        "/",
        "/chosen",
        "/memory@80000000",
        "/memory@80000000/bank",
        "/soc",
    ]


def test_removing_a_node_drops_its_properties_and_children() -> None:
    tree = without_node(parse(reference_blob()), "/memory@80000000")

    assert node_paths(tree) == ["/", "/chosen", "/soc"]
    assert node_paths(parse(serialize(tree))) == ["/", "/chosen", "/soc"]
    assert len(serialize(tree)) < len(reference_blob())


def test_added_property_grows_the_tree_by_its_padded_size() -> None:
    original = parse(reference_blob())

    tree = with_property(original, "/chosen", "padding", bytes(70001))

    reparsed = parse(serialize(tree))
    assert node_paths(reparsed) == node_paths(original)
    assert len(reparsed.structure) - len(original.structure) == 4 + 8 + 70004
    assert reparsed.strings == STRINGS + b"padding\0"
    assert len(serialize(tree)) > 65536


@pytest.mark.parametrize("path", ["/missing", "/memory", "/"])
def test_only_existing_child_nodes_can_be_removed(path: str) -> None:
    with pytest.raises(CheckError, match="no removable node"):
        without_node(parse(reference_blob()), path)


def test_property_needs_an_existing_node() -> None:
    with pytest.raises(CheckError, match="no node /missing"):
        with_property(parse(reference_blob()), "/missing", "padding", b"")


@pytest.mark.parametrize(
    "blob",
    [
        b"",
        reference_blob()[:39],
        b"\0\0\0\0" + reference_blob()[4:],
        reference_blob()[:-20],
        reference_blob().replace(TOKEN.pack(END), TOKEN.pack(7)),
    ],
)
def test_malformed_blobs_are_rejected(blob: bytes) -> None:
    with pytest.raises(CheckError, match="malformed device tree"):
        parse(blob)
