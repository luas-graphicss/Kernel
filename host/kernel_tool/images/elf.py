import struct
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.outcome import CheckError

MAGIC = b"\x7fELF"
CLASS_64_BIT = 2
DATA_LITTLE_ENDIAN = 1
CLASS_OFFSET = 4
DATA_OFFSET = 5
FILE_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIQQQQQQ")
SECTION_HEADER = struct.Struct("<IIQQQQIIQQ")
SYMBOL = struct.Struct("<IBBHQQ")

TYPE_EXECUTABLE = 2
MACHINE_RISCV = 243
SEGMENT_LOAD = 1
SEGMENT_DYNAMIC = 2
SEGMENT_INTERPRETER = 3
FLAG_EXECUTE = 1
FLAG_WRITE = 2
SECTION_SYMBOL_TABLE = 2
SECTION_UNDEFINED = 0


@dataclass(frozen=True, slots=True)
class Segment:
    kind: int
    flags: int
    address: int
    file_bytes: int
    memory_bytes: int


@dataclass(frozen=True, slots=True)
class ElfImage:
    kind: int
    machine: int
    entry: int
    segments: tuple[Segment, ...]
    undefined_symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Section:
    kind: int
    offset: int
    size: int
    link: int
    entry_size: int


def read_elf(path: Path) -> ElfImage:
    data = path.read_bytes()
    try:
        return _parse(data)
    except (struct.error, ValueError, UnicodeDecodeError) as error:
        raise CheckError(
            f"{path} is not a well-formed 64-bit little-endian ELF: {error}"
        ) from error


def _parse(data: bytes) -> ElfImage:
    (
        identity,
        kind,
        machine,
        _version,
        entry,
        program_offset,
        section_offset,
        _flags,
        _header_size,
        program_entry_size,
        program_count,
        section_entry_size,
        section_count,
        _names_index,
    ) = FILE_HEADER.unpack_from(data)
    if not identity.startswith(MAGIC):
        raise ValueError("missing ELF magic")
    if identity[CLASS_OFFSET] != CLASS_64_BIT or identity[DATA_OFFSET] != DATA_LITTLE_ENDIAN:
        raise ValueError("not a 64-bit little-endian image")

    segments = tuple(
        _segment(data, program_offset + index * program_entry_size)
        for index in range(program_count)
    )
    sections = [
        _section(data, section_offset + index * section_entry_size)
        for index in range(section_count)
    ]
    return ElfImage(
        kind=kind,
        machine=machine,
        entry=entry,
        segments=segments,
        undefined_symbols=tuple(_undefined_symbols(data, sections)),
    )


def _segment(data: bytes, offset: int) -> Segment:
    kind, flags, _offset, address, _physical, file_bytes, memory_bytes, _alignment = (
        PROGRAM_HEADER.unpack_from(data, offset)
    )
    return Segment(
        kind=kind, flags=flags, address=address, file_bytes=file_bytes, memory_bytes=memory_bytes
    )


def _section(data: bytes, offset: int) -> _Section:
    _name, kind, _flags, _address, start, size, link, _info, _alignment, entry_size = (
        SECTION_HEADER.unpack_from(data, offset)
    )
    return _Section(kind=kind, offset=start, size=size, link=link, entry_size=entry_size)


def _undefined_symbols(data: bytes, sections: list[_Section]) -> list[str]:
    undefined = []
    for section in sections:
        if section.kind != SECTION_SYMBOL_TABLE:
            continue
        names = sections[section.link]
        for offset in range(section.offset, section.offset + section.size, SYMBOL.size):
            name_offset, _info, _other, section_index, _value, _size = SYMBOL.unpack_from(
                data, offset
            )
            name = _text(data, names.offset + name_offset)
            if section_index == SECTION_UNDEFINED and name:
                undefined.append(name)
    return undefined


def _text(data: bytes, offset: int) -> str:
    return data[offset : data.index(b"\0", offset)].decode("ascii")
