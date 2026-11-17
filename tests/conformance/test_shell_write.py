import pytest

from kernel_apps.shell.commands.files import write_file
from kernel_protocol.errors.codes import ALREADY_EXISTS, NO_SPACE, KernelError
from kernel_protocol.services.files import OPEN_EXCLUSIVE, OPEN_TRUNCATE

REFUSED = "the test refuses this request"
PATH = b"data/note"
OLD_CONTENT = b"kept\n"


class StoredFile:
    def __init__(self, volume: "Volume", path: bytes) -> None:
        self._volume = volume
        self._path = path
        self.is_open = True

    def write(self, offset: int, data: bytes) -> int:
        if len(data) > self._volume.free_bytes:
            raise KernelError(NO_SPACE, REFUSED)
        self._volume.files[self._path] = data
        return len(data)

    def close(self) -> None:
        self.is_open = False


class Volume:
    def __init__(self, free_bytes: int, files: dict[bytes, bytes]) -> None:
        self.free_bytes = free_bytes
        self.files = files
        self.opened: list[StoredFile] = []

    def open(self, path: bytes, flags: int) -> StoredFile:
        if flags & OPEN_EXCLUSIVE and path in self.files:
            raise KernelError(ALREADY_EXISTS, REFUSED)
        if flags & OPEN_EXCLUSIVE or flags & OPEN_TRUNCATE:
            self.files[path] = b""
        self.opened.append(StoredFile(self, path))
        return self.opened[-1]

    def remove(self, path: bytes) -> None:
        del self.files[path]


class Storage:
    def __init__(self, volume: Volume) -> None:
        self._volume = volume
        self.written: list[str] = []

    def files(self) -> Volume:
        return self._volume

    def write(self, text: str) -> None:
        self.written.append(text)


def test_write_stores_the_line_and_reports_its_size() -> None:
    volume = Volume(free_bytes=64, files={})
    storage = Storage(volume)

    write_file(storage, ["data/note", "two", "words"])

    assert volume.files == {PATH: b"two words\n"}
    assert storage.written == ["write: bytes=10"]
    assert not volume.opened[0].is_open


def test_write_that_finds_no_space_leaves_no_new_file_behind() -> None:
    volume = Volume(free_bytes=4, files={})

    with pytest.raises(KernelError) as failure:
        write_file(Storage(volume), ["data/note", "too long for the volume"])

    assert failure.value.code == NO_SPACE
    assert volume.files == {}
    assert not volume.opened[0].is_open


def test_write_that_finds_no_space_keeps_the_entry_of_a_file_that_existed() -> None:
    volume = Volume(free_bytes=4, files={PATH: OLD_CONTENT})

    with pytest.raises(KernelError) as failure:
        write_file(Storage(volume), ["data/note", "too long for the volume"])

    assert failure.value.code == NO_SPACE
    assert volume.files == {PATH: b""}
    assert not volume.opened[-1].is_open
