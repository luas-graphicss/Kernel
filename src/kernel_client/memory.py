import _process
from kernel_client.calls import check, scalar
from kernel_protocol.syscalls.numbers import BUFFER_CREATE


class Mapping:
    def __init__(self, handle: int, writable: bool) -> None:
        self._token = check(_process.buffer_map(handle, writable))
        self.size = _process.buffer_size(self._token)

    def read(self, offset: int, length: int) -> bytes:
        return _process.buffer_read(self._token, offset, length)

    def write(self, offset: int, data: bytes) -> None:
        _process.buffer_write(self._token, offset, data)

    def unmap(self) -> None:
        check(_process.buffer_unmap(self._token))


def create_buffer(size: int) -> int:
    return scalar(BUFFER_CREATE, size)
