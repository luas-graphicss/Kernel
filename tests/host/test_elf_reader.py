from dataclasses import replace
from pathlib import Path

import pytest

from kernel_tool.images.elf import (
    FILE_HEADER,
    FLAG_EXECUTE,
    FLAG_WRITE,
    MACHINE_RISCV,
    PROGRAM_HEADER,
    SECTION_HEADER,
    SECTION_SYMBOL_TABLE,
    SEGMENT_INTERPRETER,
    SEGMENT_LOAD,
    SYMBOL,
    TYPE_EXECUTABLE,
    ElfImage,
    Segment,
    read_elf,
)
from kernel_tool.outcome import CheckError
from kernel_tool.verification.artifacts import AddressRange, image_problems

BASE = 0x80200000
BOUNDS = AddressRange(BASE, BASE + 0x100000)
IDENTITY = b"\x7fELF\x02\x01\x01" + bytes(9)
STRING_TABLE = b"\0defined\0missing\0"


def elf_file(identity: bytes = IDENTITY) -> bytes:
    segments = PROGRAM_HEADER.pack(SEGMENT_LOAD, 5, 0, BASE, BASE, 0x400, 0x400, 0x1000)
    symbols = (
        SYMBOL.pack(0, 0, 0, 0, 0, 0)
        + SYMBOL.pack(1, 0x12, 0, 1, BASE, 4)
        + SYMBOL.pack(9, 0x10, 0, 0, 0, 0)
    )
    program_offset = FILE_HEADER.size
    symbols_offset = program_offset + len(segments)
    strings_offset = symbols_offset + len(symbols)
    sections_offset = strings_offset + len(STRING_TABLE)
    sections = (
        SECTION_HEADER.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        + SECTION_HEADER.pack(
            0, SECTION_SYMBOL_TABLE, 0, 0, symbols_offset, len(symbols), 2, 1, 8, SYMBOL.size
        )
        + SECTION_HEADER.pack(0, 3, 0, 0, strings_offset, len(STRING_TABLE), 0, 0, 1, 0)
    )
    header = FILE_HEADER.pack(
        identity,
        TYPE_EXECUTABLE,
        MACHINE_RISCV,
        1,
        BASE,
        program_offset,
        sections_offset,
        0,
        FILE_HEADER.size,
        PROGRAM_HEADER.size,
        1,
        SECTION_HEADER.size,
        3,
        2,
    )
    return header + segments + symbols + STRING_TABLE + sections


REFERENCE_IMAGE = ElfImage(
    kind=TYPE_EXECUTABLE,
    machine=MACHINE_RISCV,
    entry=BASE,
    segments=(Segment(SEGMENT_LOAD, 5, BASE, 0x400, 0x400),),
    undefined_symbols=(),
)


def image(**changes: object) -> ElfImage:
    return replace(REFERENCE_IMAGE, **changes)


def test_reader_reports_segments_entry_and_undefined_symbols(tmp_path: Path) -> None:
    path = tmp_path / "image.elf"
    path.write_bytes(elf_file())

    parsed = read_elf(path)

    assert parsed.kind == TYPE_EXECUTABLE
    assert parsed.machine == MACHINE_RISCV
    assert parsed.entry == BASE
    assert parsed.segments == (Segment(SEGMENT_LOAD, 5, BASE, 0x400, 0x400),)
    assert parsed.undefined_symbols == ("missing",)


@pytest.mark.parametrize(
    "content",
    [b"", b"\x7fELF", elf_file(b"\x7fELF\x01\x01\x01" + bytes(9)), elf_file()[:100]],
)
def test_reader_rejects_other_files(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "image.elf"
    path.write_bytes(content)

    with pytest.raises(CheckError, match="not a well-formed"):
        read_elf(path)


def test_static_image_inside_its_region_has_no_problems() -> None:
    assert image_problems(image(), BOUNDS, BASE) == []


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"kind": 3}, "not a statically linked RISC-V executable"),
        ({"machine": 62}, "not a statically linked RISC-V executable"),
        ({"undefined_symbols": ("printf", "malloc")}, "2 undefined symbols: printf, malloc"),
        ({"entry": BASE + 0x800}, "entry is 0x80200800, expected 0x80200000"),
        ({"segments": ()}, "has no loadable segment"),
        (
            {
                "segments": (
                    Segment(SEGMENT_LOAD, 5, BASE, 0x400, 0x400),
                    Segment(SEGMENT_INTERPRETER, 4, BASE, 16, 16),
                )
            },
            "requests a dynamic loader",
        ),
        (
            {"segments": (Segment(SEGMENT_LOAD, FLAG_WRITE | FLAG_EXECUTE, BASE, 0x400, 0x400),)},
            "is writable and executable",
        ),
        (
            {"segments": (Segment(SEGMENT_LOAD, 5, BASE, 0x400, 0x200000),)},
            "leaves its region",
        ),
        (
            {"segments": (Segment(SEGMENT_LOAD, 4, BASE, 0x400, 0x400),)},
            "is not inside an executable segment",
        ),
    ],
)
def test_each_violation_is_reported(changes: dict[str, object], problem: str) -> None:
    assert any(problem in reported for reported in image_problems(image(**changes), BOUNDS, BASE))
