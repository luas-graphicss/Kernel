from kernel_protocol.errors.codes import INVALID_ARGUMENT, READ_ONLY, UNSUPPORTED, KernelError
from kernel_protocol.services.files import KIND_DIRECTORY
from kernel_services.filesystem.mounts import Mount, MountTable


class Location:
    def __init__(self, mount: Mount | None, node: object) -> None:
        self.mount = mount
        self.node = node

    def retain(self) -> None:
        if self.mount is not None:
            self.mount.backend.retain(self.node)

    def release(self) -> None:
        if self.mount is not None:
            self.mount.backend.release(self.node)


def mounted(location: Location) -> Mount:
    if location.mount is None:
        raise KernelError(READ_ONLY, "mount points are not created, changed or removed")
    return location.mount


def same_mount(first: Location, second: Location) -> Mount:
    mount = mounted(first)
    if mounted(second) is not mount:
        raise KernelError(UNSUPPORTED, "a rename does not cross mounts")
    return mount


class Resolver:
    def __init__(self, mounts: MountTable) -> None:
        self._mounts = mounts

    def top(self) -> Location:
        return Location(None, None)

    def walk(self, start: Location, components: list[bytes]) -> Location:
        location = start
        for name in components:
            if location.mount is None:
                mount = self._mounts.find(name)
                location = Location(mount, mount.backend.root())
            else:
                node = location.mount.backend.lookup(location.node, name)
                location = Location(location.mount, node)
        return location

    def parent(self, start: Location, components: list[bytes]) -> tuple[Location, bytes]:
        if not components:
            raise KernelError(INVALID_ARGUMENT, "the root of a namespace has no name to change")
        return self.walk(start, components[:-1]), components[-1]

    def kind(self, location: Location) -> int:
        if location.mount is None:
            return KIND_DIRECTORY
        return location.mount.backend.kind(location.node)

    def size(self, location: Location) -> int:
        if location.mount is None:
            return 0
        return location.mount.backend.size(location.node)

    def listing(self, location: Location) -> list[tuple[bytes, int, int]]:
        if location.mount is None:
            return self._mounts.listing()
        return location.mount.backend.listing(location.node)
