import re
from dataclasses import dataclass
from pathlib import Path

MEMORY_MAP_MARKER = "Linker script and memory map"
CONTRIBUTION = re.compile(r"^\s+(?:\S+\s+)?0x[0-9a-f]+\s+0x[0-9a-f]+\s+(\S+\.o\)?)$")
ARCHIVE_MEMBER = re.compile(r"^(?P<archive>.+\.a)\((?P<member>[^)]+)\)$")
COMPILER_LIBRARY = "libgcc.a"


@dataclass(frozen=True, slots=True)
class LinkOrigins:
    compiler_library_members: tuple[str, ...]
    foreign: tuple[str, ...]


def contributing_inputs(map_text: str) -> list[str]:
    _, marker, memory_map = map_text.partition(MEMORY_MAP_MARKER)
    if not marker:
        return []
    inputs = {
        match.group(1)
        for line in memory_map.splitlines()
        if (match := CONTRIBUTION.match(line)) is not None
    }
    return sorted(inputs)


def classify_origins(inputs: list[str], build_dir: Path, compiler_root: Path) -> LinkOrigins:
    build_root = build_dir.resolve()
    compiler = compiler_root.resolve()
    members = []
    foreign = []
    for name in inputs:
        archive = ARCHIVE_MEMBER.match(name)
        path = Path(archive.group("archive") if archive else name).resolve()
        if path.is_relative_to(build_root):
            continue
        if archive and path.name == COMPILER_LIBRARY and path.is_relative_to(compiler):
            members.append(archive.group("member"))
        else:
            foreign.append(name)
    return LinkOrigins(compiler_library_members=tuple(members), foreign=tuple(foreign))
