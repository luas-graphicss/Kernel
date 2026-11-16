from pathlib import Path

import pytest

from kernel_services.filesystem.boot.layout import (
    ABI_VERSION,
    BLOCK_BYTES,
    HEADER_RUNTIME,
    MAX_ENTRIES,
    MAX_FILE_BYTES,
)
from kernel_tool.outcome import CheckError
from kernel_tool.storage.boot_image import (
    MANIFEST,
    RELEASE_PATH,
    BootFile,
    build_image,
    load_files,
    read_image,
    release_file,
    runtime_tag,
    write_boot_image,
)
from kernel_tool.toolchain.lock import load_lock

REPOSITORY = Path(__file__).resolve().parents[2]
RUNTIME = b"micropython-1.29"
OTHER_RUNTIME = b"micropython-1.30"
LICENSE_TEXT = b"license text\n"
FILES = (
    BootFile("system/license", LICENSE_TEXT),
    BootFile("etc/motd", b"hello\n"),
    BootFile("empty", b""),
)
LICENSE_ENTRY = '[[file]]\npath = "system/license"\nsource = "LICENSE"\n'


def flipped(image: bytes, offset: int) -> bytes:
    damaged = bytearray(image)
    damaged[offset] ^= 0xFF
    return bytes(damaged)


def repository_with(directory: Path, manifest: str) -> Path:
    root = directory / "repository"
    (root / MANIFEST).parent.mkdir(parents=True)
    (root / MANIFEST).write_text(manifest, encoding="utf-8")
    (root / "LICENSE").write_bytes(LICENSE_TEXT)
    (directory / "outside").write_bytes(b"outside the repository\n")
    return root


def test_the_runtime_tag_names_the_pinned_interpreter_release() -> None:
    assert runtime_tag(load_lock(REPOSITORY / "toolchain.lock.toml")) == RUNTIME


def test_the_release_file_states_the_interface_and_the_runtime() -> None:
    content = f"abi={ABI_VERSION}\nruntime=micropython-1.29\n".encode("ascii")

    assert release_file(RUNTIME) == BootFile(RELEASE_PATH, content)


def test_an_image_gives_back_every_file_whatever_the_order_they_were_listed() -> None:
    image = build_image(FILES, RUNTIME)

    assert len(image) % BLOCK_BYTES == 0
    assert read_image(image, RUNTIME) == {file.path: file.content for file in FILES}
    assert build_image(tuple(reversed(FILES)), RUNTIME) == image


def test_an_image_built_for_another_runtime_is_refused() -> None:
    image = build_image(FILES, RUNTIME)

    with pytest.raises(CheckError, match="another Python runtime"):
        read_image(image, OTHER_RUNTIME)


def test_a_damaged_image_is_refused() -> None:
    image = build_image(FILES, RUNTIME)

    with pytest.raises(CheckError, match="boot image refused"):
        read_image(flipped(image, HEADER_RUNTIME), RUNTIME)
    with pytest.raises(CheckError, match="boot image refused"):
        read_image(flipped(image, BLOCK_BYTES), RUNTIME)
    with pytest.raises(CheckError, match="boot image refused"):
        read_image(flipped(image, len(image) - BLOCK_BYTES), RUNTIME)
    with pytest.raises(CheckError, match="boot image refused"):
        read_image(image[:-BLOCK_BYTES], RUNTIME)


@pytest.mark.parametrize(
    ("files", "problem"),
    [
        ((BootFile("../escape", b""),), "is not valid"),
        ((BootFile("/absolute", b""),), "is not valid"),
        ((BootFile("double//separator", b""),), "is not valid"),
        ((BootFile("", b""),), "is not valid"),
        ((BootFile("same", b"1"), BootFile("same", b"2")), "repeat a path"),
        ((BootFile("large", bytes(MAX_FILE_BYTES + 1)),), "exceeds"),
        (tuple(BootFile(f"file-{number}", b"") for number in range(MAX_ENTRIES + 1)), "at most"),
    ],
    ids=["parent", "absolute", "empty-name", "empty-path", "repeated", "too-large", "too-many"],
)
def test_files_that_do_not_fit_the_format_are_refused(
    files: tuple[BootFile, ...], problem: str
) -> None:
    with pytest.raises(CheckError, match=problem):
        build_image(files, RUNTIME)


def test_the_largest_file_and_the_largest_table_fit() -> None:
    largest = BootFile("largest", bytes(MAX_FILE_BYTES))
    most = tuple(BootFile(f"file-{number}", b"") for number in range(MAX_ENTRIES))

    assert read_image(build_image((largest,), RUNTIME), RUNTIME) == {"largest": largest.content}
    assert len(read_image(build_image(most, RUNTIME), RUNTIME)) == MAX_ENTRIES


def test_the_manifest_copies_files_of_the_repository_into_the_image(tmp_path: Path) -> None:
    root = repository_with(tmp_path, LICENSE_ENTRY)

    assert load_files(root) == (BootFile("system/license", LICENSE_TEXT),)
    assert load_files(repository_with(tmp_path / "empty", "")) == ()


@pytest.mark.parametrize(
    ("manifest", "problem"),
    [
        ('[[file]]\npath = "outside"\nsource = "../outside"\n', "is not a file of the repository"),
        ('[[file]]\npath = "missing"\nsource = "missing"\n', "is not a file of the repository"),
        ('[[file]]\npath = "directory"\nsource = "config"\n', "is not a file of the repository"),
        ('[[file]]\npath = "system/license"\n', "exactly a path and a source"),
        (LICENSE_ENTRY + 'mode = "0644"\n', "exactly a path and a source"),
        ('[[file]]\npath = 5\nsource = "LICENSE"\n', "path and source must be strings"),
        ('title = "boot"\n', "only \\[\\[file\\]\\] tables are allowed"),
        ("[[file", "manifest.toml"),
    ],
)
def test_a_manifest_that_leaves_the_repository_or_is_malformed_is_refused(
    tmp_path: Path, manifest: str, problem: str
) -> None:
    root = repository_with(tmp_path, manifest)

    with pytest.raises(CheckError, match=problem):
        load_files(root)


def test_the_boot_image_of_the_repository_holds_the_license_and_the_release(
    tmp_path: Path,
) -> None:
    output = tmp_path / "boot.img"

    write_boot_image(REPOSITORY, load_lock(REPOSITORY / "toolchain.lock.toml"), output)
    files = read_image(output.read_bytes(), RUNTIME)

    assert set(files) == {"system/license", RELEASE_PATH}
    assert files["system/license"] == (REPOSITORY / "LICENSE").read_bytes()
    assert files[RELEASE_PATH] == release_file(RUNTIME).content
