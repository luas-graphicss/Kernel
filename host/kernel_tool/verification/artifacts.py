from dataclasses import asdict, dataclass
from pathlib import Path

from kernel_tool.build.native import BuildOutputs, link_map
from kernel_tool.images.elf import (
    FLAG_EXECUTE,
    FLAG_WRITE,
    MACHINE_RISCV,
    SEGMENT_DYNAMIC,
    SEGMENT_INTERPRETER,
    SEGMENT_LOAD,
    TYPE_EXECUTABLE,
    ElfImage,
    read_elf,
)
from kernel_tool.images.link_map import classify_origins, contributing_inputs
from kernel_tool.images.user_image import read_header
from kernel_tool.profiles.model import Profile
from kernel_tool.toolchain.fetch import sha256_file
from kernel_tool.toolchain.resolve import Toolchain

REPORTED_SYMBOLS = 8
PAGE_BYTES = 4096


@dataclass(frozen=True, slots=True)
class AddressRange:
    start: int
    end: int

    def contains(self, address: int, length: int) -> bool:
        return self.start <= address and address + length <= self.end


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    name: str
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ExecutableRecord:
    name: str
    entry: int
    load_segments: tuple[dict[str, int], ...]
    compiler_library_members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArtifactReport:
    artifacts: tuple[ArtifactRecord, ...]
    executables: tuple[ExecutableRecord, ...]
    problems: tuple[str, ...]

    def to_document(self) -> dict[str, object]:
        return asdict(self)


def verify_artifacts(
    outputs: BuildOutputs, profile: Profile, toolchain: Toolchain
) -> ArtifactReport:
    layout = profile.layout
    supervisor = AddressRange(layout.kernel_base, layout.kernel_base + profile.limits.memory_bytes)
    user = AddressRange(layout.user_region_base, layout.user_region_base + layout.user_region_bytes)
    expectations = (
        (outputs.kernel, supervisor, layout.kernel_base),
        (outputs.selftest_kernel, supervisor, layout.kernel_base),
        *((program, user, None) for program in outputs.user_programs),
    )

    executables = []
    problems: list[str] = []
    for path, bounds, entry in expectations:
        image = read_elf(path)
        inputs = contributing_inputs(link_map(path).read_text(encoding="utf-8"))
        origins = classify_origins(inputs, outputs.directory, toolchain.compiler_root)
        if not inputs:
            problems.append(f"{path.name}: its link map lists no input")
        problems.extend(
            f"{path.name}: {problem}" for problem in image_problems(image, bounds, entry)
        )
        problems.extend(
            f"{path.name}: links {origin} from outside the build" for origin in origins.foreign
        )
        executables.append(_executable_record(path, image, origins.compiler_library_members))
    for path in outputs.user_images:
        problems.extend(f"{path.name}: {problem}" for problem in user_image_problems(path, profile))

    return ArtifactReport(
        artifacts=tuple(_artifact_record(path) for path in outputs.artifacts),
        executables=tuple(executables),
        problems=tuple(problems),
    )


def image_problems(image: ElfImage, bounds: AddressRange, entry: int | None) -> list[str]:
    problems = []
    if image.kind != TYPE_EXECUTABLE or image.machine != MACHINE_RISCV:
        problems.append("is not a statically linked RISC-V executable")
    if any(segment.kind in (SEGMENT_DYNAMIC, SEGMENT_INTERPRETER) for segment in image.segments):
        problems.append("requests a dynamic loader")
    if image.undefined_symbols:
        listed = ", ".join(image.undefined_symbols[:REPORTED_SYMBOLS])
        problems.append(f"has {len(image.undefined_symbols)} undefined symbols: {listed}")
    if entry is not None and image.entry != entry:
        problems.append(f"entry is {image.entry:#x}, expected {entry:#x}")

    loaded = [segment for segment in image.segments if segment.kind == SEGMENT_LOAD]
    if not loaded:
        problems.append("has no loadable segment")
    for segment in loaded:
        if segment.flags & FLAG_WRITE and segment.flags & FLAG_EXECUTE:
            problems.append(f"segment at {segment.address:#x} is writable and executable")
        if not bounds.contains(segment.address, segment.memory_bytes):
            problems.append(f"segment at {segment.address:#x} leaves its region")
    if not any(
        segment.flags & FLAG_EXECUTE
        and segment.address <= image.entry < segment.address + segment.memory_bytes
        for segment in loaded
    ):
        problems.append(f"entry {image.entry:#x} is not inside an executable segment")
    return problems


def user_image_problems(path: Path, profile: Profile) -> list[str]:
    layout = profile.layout
    image = path.read_bytes()
    header = read_header(image)
    problems = []
    if header.load_base != layout.user_region_base:
        problems.append(f"loads at {header.load_base:#x} instead of the user region")
    if header.memory_bytes > layout.user_region_bytes:
        problems.append(f"needs {header.memory_bytes} bytes, more than the user region")
    if header.file_bytes != len(image):
        problems.append(f"declares {header.file_bytes} bytes but the file has {len(image)}")
    if any(
        size % PAGE_BYTES
        for size in (header.text_bytes, header.rodata_bytes, header.data_bytes, header.stack_bytes)
    ):
        problems.append("has a segment that is not a whole number of pages")
    if header.heap_bytes > profile.limits.process_heap_bytes:
        problems.append(f"reserves a heap of {header.heap_bytes} bytes, above the process limit")
    return problems


def differing_artifacts(first: BuildOutputs, second: BuildOutputs) -> list[str]:
    return [
        original.name
        for original, rebuilt in zip(first.artifacts, second.artifacts, strict=True)
        if sha256_file(original) != sha256_file(rebuilt)
    ]


def _artifact_record(path: Path) -> ArtifactRecord:
    return ArtifactRecord(name=path.name, bytes=path.stat().st_size, sha256=sha256_file(path))


def _executable_record(path: Path, image: ElfImage, members: tuple[str, ...]) -> ExecutableRecord:
    return ExecutableRecord(
        name=path.name,
        entry=image.entry,
        load_segments=tuple(
            {"address": segment.address, "bytes": segment.memory_bytes, "flags": segment.flags}
            for segment in image.segments
            if segment.kind == SEGMENT_LOAD
        ),
        compiler_library_members=members,
    )
