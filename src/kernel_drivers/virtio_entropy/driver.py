from kernel_client import capabilities, memory
from kernel_drivers.virtio.transport import Transport
from kernel_protocol.errors.codes import INVALID_ARGUMENT, IO_ERROR, UNKNOWN_OUTCOME, KernelError

VIRTIO_MODEL = 4
NO_FEATURES = 0
MAX_BYTES = 256
BUFFER_BYTES = 4096


class EntropyDriver:
    def __init__(self, device: int, timeout_nanoseconds: int) -> None:
        self._timeout = timeout_nanoseconds
        self._transport = Transport(device, NO_FEATURES)
        self._buffer = memory.create_buffer(BUFFER_BYTES)
        self._mapping = memory.Mapping(self._buffer, True)

    def read(self, count: int) -> bytes:
        if count < 1 or count > MAX_BYTES:
            raise KernelError(INVALID_ARGUMENT, "entropy request outside one transfer")
        written = self._fill(count)
        collected = self._mapping.read(0, written)
        self._mapping.write(0, bytes(written))
        return collected

    def _fill(self, count: int) -> int:
        try:
            return self._transport.transfer(((self._buffer, 0, count, True),), self._timeout)
        except KernelError as error:
            if error.code != UNKNOWN_OUTCOME:
                raise
        raise KernelError(IO_ERROR, "the entropy device did not answer")

    def close(self) -> None:
        self._transport.close()
        self._mapping.unmap()
        capabilities.close(self._buffer)
