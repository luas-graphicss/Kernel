from kernel_protocol.errors.codes import NOT_FOUND, OK, KernelError
from kernel_protocol.services.files import KIND_DIRECTORY, MODE_READ_ONLY, MountReport
from kernel_services.filesystem.backends.base import Backend

UNAVAILABLE = b"unavailable"


class Mount:
    def __init__(self, name: bytes, backend: Backend) -> None:
        self.name = name
        self.backend = backend


class MountTable:
    def __init__(self) -> None:
        self._mounts: dict[bytes, Mount] = {}
        self._failures: dict[bytes, int] = {}

    def add(self, name: bytes, backend: Backend) -> None:
        self._mounts[name] = Mount(name, backend)

    def fail(self, name: bytes, code: int) -> None:
        self._failures[name] = code

    def find(self, name: bytes) -> Mount:
        mount = self._mounts.get(name)
        if mount is None:
            raise KernelError(NOT_FOUND, "nothing is mounted under the name")
        return mount

    def listing(self) -> list[tuple[bytes, int, int]]:
        return [(name, KIND_DIRECTORY, 0) for name in sorted(self._mounts)]

    def reports(self) -> list[MountReport]:
        reports = []
        for name in sorted(self._mounts):
            described = self._mounts[name].backend.describe()
            reports.append(
                MountReport(
                    name,
                    OK,
                    described.mode,
                    bytes(described.reason, "utf-8"),
                    described.generation,
                    described.free_blocks,
                    described.total_blocks,
                )
            )
        for name in sorted(self._failures):
            reports.append(
                MountReport(name, self._failures[name], MODE_READ_ONLY, UNAVAILABLE, 0, 0, 0)
            )
        return reports

    def sync(self) -> None:
        for name in sorted(self._mounts):
            self._mounts[name].backend.sync()

    def close(self) -> None:
        for name in sorted(self._mounts):
            self._mounts[name].backend.close()
