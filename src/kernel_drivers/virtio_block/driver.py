from kernel_client import capabilities, devices, memory
from kernel_drivers.virtio.transport import Transport
from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    IO_ERROR,
    READ_ONLY,
    UNKNOWN_OUTCOME,
    UNSUPPORTED,
    KernelError,
)

VIRTIO_MODEL = 2
FEATURE_READ_ONLY = 1 << 5
FEATURE_FLUSH = 1 << 9
SECTOR_BYTES = 512
IDENTITY_BYTES = 20

REQUEST_READ = 0
REQUEST_WRITE = 1
REQUEST_FLUSH = 4
REQUEST_IDENTITY = 8
STATUS_OK = 0
STATUS_UNSUPPORTED = 2
STATUS_PENDING = b"\xff"

CONTROL_BYTES = 4096
HEADER_OFFSET = 0
HEADER_BYTES = 16
STATUS_OFFSET = 16
STATUS_BYTES = 1
IDENTITY_OFFSET = 512
CAPACITY_OFFSET = 0
CAPACITY_BYTES = 8


class BlockDriver:
    def __init__(self, device: int, timeout_nanoseconds: int) -> None:
        self._timeout = timeout_nanoseconds
        self._transport = Transport(device, FEATURE_READ_ONLY | FEATURE_FLUSH)
        self._control = memory.create_buffer(CONTROL_BYTES)
        self._mapping = memory.Mapping(self._control, True)
        features = self._transport.session.features
        capacity = devices.read_config(device, CAPACITY_OFFSET, CAPACITY_BYTES)
        self.read_only = bool(features & FEATURE_READ_ONLY)
        self.can_flush = bool(features & FEATURE_FLUSH)
        self.sectors = int.from_bytes(capacity, "little")

    def identity(self) -> bytes:
        data = (self._control, IDENTITY_OFFSET, IDENTITY_BYTES, True)
        self._request(REQUEST_IDENTITY, 0, data, False)
        return self._mapping.read(IDENTITY_OFFSET, IDENTITY_BYTES).rstrip(b"\x00")

    def read(self, sector: int, count: int, buffer: int, offset: int) -> None:
        self._check_range(sector, count)
        if count:
            data = (buffer, offset, count * SECTOR_BYTES, True)
            self._request(REQUEST_READ, sector, data, False)

    def write(self, sector: int, count: int, buffer: int, offset: int) -> None:
        if self.read_only:
            raise KernelError(READ_ONLY, "the device accepts no writes")
        self._check_range(sector, count)
        if count:
            data = (buffer, offset, count * SECTOR_BYTES, False)
            self._request(REQUEST_WRITE, sector, data, True)

    def flush(self) -> None:
        if not self.can_flush:
            raise KernelError(UNSUPPORTED, "the device has no flush command")
        self._request(REQUEST_FLUSH, 0, None, True)

    def has_failed(self) -> bool:
        return self._transport.failed

    def resets(self) -> int:
        return self._transport.resets

    def close(self) -> None:
        self._transport.close()
        self._mapping.unmap()
        capabilities.close(self._control)

    def _exchange(self, segments: tuple[tuple[int, int, int, bool], ...], has_effect: bool) -> None:
        try:
            self._transport.transfer(segments, self._timeout)
            return
        except KernelError as error:
            if error.code != UNKNOWN_OUTCOME or has_effect:
                raise
        raise KernelError(IO_ERROR, "the device did not answer the request")

    def _check_range(self, sector: int, count: int) -> None:
        if sector < 0 or count < 0 or sector + count > self.sectors:
            raise KernelError(INVALID_ARGUMENT, "sectors outside the device")

    def _request(
        self, kind: int, sector: int, data: tuple[int, int, int, bool] | None, has_effect: bool
    ) -> None:
        header = kind.to_bytes(4, "little") + bytes(4) + sector.to_bytes(8, "little")
        head = (self._control, HEADER_OFFSET, HEADER_BYTES, False)
        tail = (self._control, STATUS_OFFSET, STATUS_BYTES, True)
        self._mapping.write(HEADER_OFFSET, header)
        self._mapping.write(STATUS_OFFSET, STATUS_PENDING)
        self._exchange((head, tail) if data is None else (head, data, tail), has_effect)
        status = self._mapping.read(STATUS_OFFSET, STATUS_BYTES)[0]
        if status == STATUS_UNSUPPORTED:
            raise KernelError(UNSUPPORTED, "the device does not know the request")
        if status != STATUS_OK:
            raise KernelError(IO_ERROR, "the device reported a failed request")
