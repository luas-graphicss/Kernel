from kernel_client import capabilities, memory, services
from kernel_client.processes import clock
from kernel_protocol.errors.codes import (
    IO_ERROR,
    PEER_CLOSED,
    TIMED_OUT,
    UNKNOWN_OUTCOME,
    KernelError,
)
from kernel_protocol.identity.rights import RIGHT_DELEGATE, RIGHT_READ, RIGHT_WRITE
from kernel_protocol.services.block import (
    OPERATION_ATTACH,
    OPERATION_DETACH,
    OPERATION_FLUSH,
    OPERATION_READ,
    OPERATION_WRITE,
    Geometry,
    decode_geometry,
    encode_transfer,
)

SHARED_RIGHTS = RIGHT_READ | RIGHT_WRITE | RIGHT_DELEGATE
SERVICE_LOST_CODES = (PEER_CLOSED, TIMED_OUT)
SERVICE_LOST = "the block service stopped answering"


class BlockDevice:
    def __init__(self, endpoint: int, buffer_bytes: int, timeout_nanoseconds: int) -> None:
        self._endpoint = endpoint
        self._timeout = timeout_nanoseconds
        self._buffer = memory.create_buffer(buffer_bytes)
        self.mapping = memory.Mapping(self._buffer, True)
        try:
            self.geometry = self._attach()
        except KernelError:
            self._release()
            raise

    def read(self, sector: int, count: int, offset: int = 0) -> None:
        self._request(OPERATION_READ, encode_transfer(sector, count, offset), False)

    def write(self, sector: int, count: int, offset: int = 0) -> None:
        self._request(OPERATION_WRITE, encode_transfer(sector, count, offset), True)

    def flush(self) -> None:
        self._request(OPERATION_FLUSH, b"", True)

    def close(self) -> None:
        try:
            services.call(self._endpoint, OPERATION_DETACH, b"", deadline=self._deadline())
        except KernelError as error:
            if error.code not in SERVICE_LOST_CODES:
                raise
        self._release()

    def _attach(self) -> Geometry:
        shared = capabilities.derive(self._buffer, SHARED_RIGHTS)
        try:
            payload, _received = services.call(
                self._endpoint, OPERATION_ATTACH, b"", shared, self._deadline()
            )
        finally:
            capabilities.close(shared)
        return decode_geometry(payload)

    def _request(self, operation: int, payload: bytes, has_effect: bool) -> None:
        try:
            services.call(self._endpoint, operation, payload, deadline=self._deadline())
            return
        except KernelError as error:
            if error.code not in SERVICE_LOST_CODES:
                raise
        raise KernelError(UNKNOWN_OUTCOME if has_effect else IO_ERROR, SERVICE_LOST)

    def _deadline(self) -> int:
        return clock() + self._timeout

    def _release(self) -> None:
        self.mapping.unmap()
        capabilities.close(self._buffer)
