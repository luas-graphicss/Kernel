from kernel_client.services import Reply
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    ALREADY_EXISTS,
    INVALID_ARGUMENT,
    IS_A_DIRECTORY,
    NOT_A_DIRECTORY,
    NOT_FOUND,
    READ_ONLY,
    KernelError,
)
from kernel_protocol.services.files import (
    KIND_DIRECTORY,
    KIND_FILE,
    LIST_END,
    MAX_TRANSFER_BYTES,
    MODE_READ_ONLY,
    NAMESPACE_READ,
    NAMESPACE_WRITE,
    OPEN_CREATE,
    OPEN_DIRECTORY,
    OPEN_EXCLUSIVE,
    OPEN_KNOWN,
    OPEN_READ,
    OPEN_TRUNCATE,
    OPEN_WRITE,
    decode_count,
    decode_extent,
    decode_rename,
    decode_size,
    decode_tagged_path,
    decode_write,
    encode_count,
    encode_entries,
    encode_entry,
    encode_opened,
    encode_stat,
)
from kernel_services.filesystem.namespace.paths import split
from kernel_services.filesystem.namespace.resolver import Location, Resolver, mounted, same_mount
from kernel_services.filesystem.namespace.table import OpenFile, Registry, Session

CHANGING_FLAGS = OPEN_WRITE | OPEN_CREATE | OPEN_TRUNCATE
NO_READ = "the namespace does not grant reading"
NO_WRITE = "the namespace does not grant writing"


def require(session: Session, right: int, detail: str) -> None:
    if session.namespace.rights & right == 0:
        raise KernelError(ACCESS_DENIED, detail)


def check_open(session: Session, flags: int) -> None:
    if flags & ~OPEN_KNOWN or flags & (OPEN_READ | OPEN_WRITE | OPEN_DIRECTORY) == 0:
        raise KernelError(INVALID_ARGUMENT, "open asks for unknown flags or for no access")
    if flags & OPEN_DIRECTORY and flags & CHANGING_FLAGS:
        raise KernelError(IS_A_DIRECTORY, "a directory is opened only for listing")
    if flags & OPEN_TRUNCATE and flags & OPEN_WRITE == 0:
        raise KernelError(INVALID_ARGUMENT, "truncation needs a handle opened for writing")
    if flags & (OPEN_READ | OPEN_DIRECTORY):
        require(session, NAMESPACE_READ, NO_READ)
    if flags & CHANGING_FLAGS:
        require(session, NAMESPACE_WRITE, NO_WRITE)


class FileOperations:
    def __init__(self, registry: Registry, resolver: Resolver) -> None:
        self._registry = registry
        self._resolver = resolver

    def open(self, session: Session, body: bytes) -> Reply:
        flags, path = decode_tagged_path(body)
        components = split(path)
        check_open(session, flags)
        location = self._find_or_create(session, components, flags)
        kind = self._resolver.kind(location)
        if kind == KIND_DIRECTORY and flags & OPEN_DIRECTORY == 0:
            raise KernelError(IS_A_DIRECTORY, "the path names a directory")
        if kind != KIND_DIRECTORY and flags & OPEN_DIRECTORY:
            raise KernelError(NOT_A_DIRECTORY, "the path names a file")
        if flags & CHANGING_FLAGS and mounted(location).backend.describe().mode == MODE_READ_ONLY:
            raise KernelError(READ_ONLY, "the mount is read-only")
        if flags & OPEN_TRUNCATE:
            mounted(location).backend.truncate(location.node, 0)
        opened = self._registry.add_file(session, location, flags)
        return Reply(encode_opened(opened.handle, kind, self._resolver.size(location)))

    def close(self, opened: OpenFile, body: bytes) -> Reply:
        self._registry.close_file(opened)
        return Reply()

    def read(self, opened: OpenFile, body: bytes) -> Reply:
        offset, count = decode_extent(body)
        if opened.flags & OPEN_DIRECTORY:
            raise KernelError(IS_A_DIRECTORY, "the handle names a directory")
        if opened.flags & OPEN_READ == 0:
            raise KernelError(ACCESS_DENIED, "the handle was not opened for reading")
        if count > MAX_TRANSFER_BYTES:
            count = MAX_TRANSFER_BYTES
        location = opened.location
        return Reply(mounted(location).backend.read(location.node, offset, count))

    def write(self, opened: OpenFile, body: bytes) -> Reply:
        offset, data = decode_write(body)
        location = self._writable(opened)
        return Reply(encode_count(mounted(location).backend.write(location.node, offset, data)))

    def truncate(self, opened: OpenFile, body: bytes) -> Reply:
        location = self._writable(opened)
        mounted(location).backend.truncate(location.node, decode_size(body))
        return Reply()

    def sync(self, opened: OpenFile, body: bytes) -> Reply:
        mount = opened.location.mount
        if mount is not None:
            mount.backend.sync()
        return Reply()

    def list_directory(self, opened: OpenFile, body: bytes) -> Reply:
        cursor = decode_count(body)
        if opened.flags & OPEN_DIRECTORY == 0:
            raise KernelError(NOT_A_DIRECTORY, "the handle does not name a directory")
        listed = self._resolver.listing(opened.location)
        entries: list[bytes] = []
        used = 0
        while cursor < len(listed):
            name, kind, size = listed[cursor]
            entry = encode_entry(name, kind, size)
            if used + len(entry) > MAX_TRANSFER_BYTES:
                return Reply(encode_entries(cursor, entries))
            entries.append(entry)
            used += len(entry)
            cursor += 1
        return Reply(encode_entries(LIST_END, entries))

    def stat(self, session: Session, body: bytes) -> Reply:
        require(session, NAMESPACE_READ, NO_READ)
        location = self._resolver.walk(session.namespace.root, split(body))
        return Reply(encode_stat(self._resolver.kind(location), self._resolver.size(location)))

    def make_directory(self, session: Session, body: bytes) -> Reply:
        require(session, NAMESPACE_WRITE, NO_WRITE)
        directory, name = self._resolver.parent(session.namespace.root, split(body))
        mounted(directory).backend.create(directory.node, name, KIND_DIRECTORY)
        return Reply()

    def remove(self, session: Session, body: bytes) -> Reply:
        require(session, NAMESPACE_WRITE, NO_WRITE)
        directory, name = self._resolver.parent(session.namespace.root, split(body))
        mounted(directory).backend.remove(directory.node, name)
        return Reply()

    def rename(self, session: Session, body: bytes) -> Reply:
        require(session, NAMESPACE_WRITE, NO_WRITE)
        source_path, target_path = decode_rename(body)
        root = session.namespace.root
        source, source_name = self._resolver.parent(root, split(source_path))
        target, target_name = self._resolver.parent(root, split(target_path))
        same_mount(source, target).backend.rename(
            source.node, source_name, target.node, target_name
        )
        return Reply()

    def _find_or_create(self, session: Session, components: list[bytes], flags: int) -> Location:
        root = session.namespace.root
        try:
            location = self._resolver.walk(root, components)
        except KernelError as error:
            if error.code != NOT_FOUND or flags & OPEN_CREATE == 0:
                raise
            directory, name = self._resolver.parent(root, components)
            mount = mounted(directory)
            return Location(mount, mount.backend.create(directory.node, name, KIND_FILE))
        if flags & OPEN_CREATE and flags & OPEN_EXCLUSIVE:
            raise KernelError(ALREADY_EXISTS, "the path already names an entry")
        return location

    def _writable(self, opened: OpenFile) -> Location:
        if opened.flags & OPEN_WRITE == 0:
            raise KernelError(ACCESS_DENIED, "the handle was not opened for writing")
        return opened.location
