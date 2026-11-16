from pathlib import Path

from kernel_tool.images.user_image import HEADER, MAGIC, VERSION
from kernel_tool.profiles.loader import DEFAULT_PROFILE, load_profile
from kernel_tool.verification.artifacts import user_image_problems

REPOSITORY = Path(__file__).resolve().parents[2]
PROFILE = load_profile(REPOSITORY, DEFAULT_PROFILE)
REGION = PROFILE.layout.user_region_base
FILE_BYTES = HEADER.size + 8


def write_image(tmp_path: Path, **changes: int) -> Path:
    fields = {
        "load_base": REGION,
        "file_bytes": FILE_BYTES,
        "memory_bytes": 0x4000,
        "entry": REGION + HEADER.size,
        "heap_bytes": 0x1000,
        "stack_bytes": 0x1000,
    } | changes
    path = tmp_path / "image.img"
    path.write_bytes(HEADER.pack(MAGIC, VERSION, *fields.values()) + bytes(8))
    return path


def test_image_built_for_the_profile_has_no_problems(tmp_path: Path) -> None:
    assert user_image_problems(write_image(tmp_path), PROFILE) == []


def test_each_mismatch_with_the_profile_is_reported(tmp_path: Path) -> None:
    path = write_image(
        tmp_path,
        load_base=REGION + 0x1000,
        file_bytes=FILE_BYTES + 1,
        memory_bytes=PROFILE.layout.user_region_bytes + 1,
        heap_bytes=PROFILE.limits.process_heap_bytes + 1,
    )

    problems = user_image_problems(path, PROFILE)

    assert len(problems) == 4
    assert "instead of the user region" in problems[0]
    assert "more than the user region" in problems[1]
    assert f"but the file has {FILE_BYTES}" in problems[2]
    assert "above the process limit" in problems[3]
