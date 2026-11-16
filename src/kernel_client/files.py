from kernel_client import services
from kernel_protocol.services.files import (
    LIST_END,
    MAX_TRANSFER_BYTES,
    OPERATION_CLOSE,
    OPERATION_DROP,
    OPERATION_ENTER,
    OPERATION_LEAVE,
    OPERATION_LIST,
    OPERATION_MAKE_DIRECTORY,
    OPERATION_OPEN,
    OPERATION_READ,
    OPERATION_REMOVE,
    OPERATION_RENAME,
    OPERATION_STAT,
    OPERATION_STATUS,
    OPERATION_SUBSPACE,
    OPERATION_SYNC,
    OPERATION_TRUNCATE,
    OPERATION_WRITE,
    MountReport,
    decode_count,
    decode_entries,
    decode_mounts,
    decode_opened,
    decode_session,
    decode_stat,
    encode_count,
    encode_extent,
    encode_rename,
    encode_request,
    encode_size,
    encode_tagged_path,
    encode_write,
)


class File:
    def __init__(self, namespace: "Namespace", handle: int, kind: int, size: int) -> None:
        self._namespace = namespace
        self.handle = handle
        self.kind = kind
        self.size = size

    def read(self, offset: int, count: int) -> bytes:
        parts = []
        collected = 0
        while collected < count:
            missing = count - collected
            wanted = missing if missing < MAX_TRANSFER_BYTES else MAX_TRANSFER_BYTES
            part = self._call(OPERATION_READ, encode_extent(offset + collected, wanted))
            if len(part) == 0:
                break
            parts.append(part)
            collected += len(part)
        return b"".join(parts)

    def write(self, offset: int, data: bytes) -> int:
        written = 0
        while written < len(data):
            chunk = data[written : written + MAX_TRANSFER_BYTES]
            accepted = decode_count(
                self._call(OPERATION_WRITE, encode_write(offset + written, chunk))
            )
            written += accepted
            if accepted < len(chunk):
                break
        return written

    def truncate(self, size: int) -> None:
        self._call(OPERATION_TRUNCATE, encode_size(size))

    def sync(self) -> None:
        self._call(OPERATION_SYNC)

    def entries(self) -> list[tuple[bytes, int, int]]:
        listed = []
        cursor = 0
        while cursor != LIST_END:
            cursor, entries = decode_entries(self._call(OPERATION_LIST, encode_count(cursor)))
            listed.extend(entries)
        return listed

    def close(self) -> None:
        self._call(OPERATION_CLOSE)

    def _call(self, operation: int, body: bytes = b"") -> bytes:
        return self._namespace.request(operation, self.handle, body)


class Namespace:
    def __init__(self, service: int, capability: int) -> None:
        self._service = service
        services.note(capability, OPERATION_ENTER)
        payload, _received = services.call(service, OPERATION_ENTER)
        self.instance, self.session, self.rights = decode_session(payload)

    def request(self, operation: int, subject: int, body: bytes = b"") -> bytes:
        payload, _received = services.call(
            self._service, operation, encode_request(self.instance, subject, body)
        )
        return payload

    def open(self, path: bytes, flags: int) -> File:
        opened = self.request(OPERATION_OPEN, self.session, encode_tagged_path(flags, path))
        handle, kind, size = decode_opened(opened)
        return File(self, handle, kind, size)

    def stat(self, path: bytes) -> tuple[int, int]:
        return decode_stat(self.request(OPERATION_STAT, self.session, path))

    def make_directory(self, path: bytes) -> None:
        self.request(OPERATION_MAKE_DIRECTORY, self.session, path)

    def remove(self, path: bytes) -> None:
        self.request(OPERATION_REMOVE, self.session, path)

    def rename(self, source: bytes, target: bytes) -> None:
        self.request(OPERATION_RENAME, self.session, encode_rename(source, target))

    def subspace(self, path: bytes, rights: int) -> tuple[int, int]:
        payload, capability = services.call(
            self._service,
            OPERATION_SUBSPACE,
            encode_request(self.instance, self.session, encode_tagged_path(rights, path)),
        )
        return decode_count(payload), capability

    def drop(self, namespace: int) -> None:
        self.request(OPERATION_DROP, self.session, encode_count(namespace))

    def status(self) -> list[MountReport]:
        return decode_mounts(self.request(OPERATION_STATUS, self.session))

    def leave(self) -> None:
        self.request(OPERATION_LEAVE, self.session)
