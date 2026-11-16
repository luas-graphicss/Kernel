from kernel_client import capabilities, ipc
from kernel_client.services import Reply, Service
from kernel_drivers.virtio_block.driver import BlockDriver
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    BAD_STATE,
    INVALID_ARGUMENT,
    LIMIT_EXCEEDED,
    UNSUPPORTED,
    KernelError,
)
from kernel_protocol.identity.rights import OBJECT_BUFFER, RIGHT_READ, RIGHT_WRITE
from kernel_protocol.services.block import (
    FLAG_FLUSH,
    FLAG_READ_ONLY,
    OPERATION_ATTACH,
    OPERATION_DETACH,
    OPERATION_EVICT,
    OPERATION_FLUSH,
    OPERATION_READ,
    OPERATION_WRITE,
    Geometry,
    decode_client,
    decode_transfer,
    encode_geometry,
)

BUFFER_RIGHTS = RIGHT_READ | RIGHT_WRITE
MAX_CLIENTS = 4


def geometry_of(driver: BlockDriver, instance: int) -> Geometry:
    flags = 0
    if driver.read_only:
        flags |= FLAG_READ_ONLY
    if driver.can_flush:
        flags |= FLAG_FLUSH
    return Geometry(driver.sectors, flags, instance, driver.identity())


class BlockService(Service):
    def __init__(self, driver: BlockDriver, geometry: Geometry, supervisor: int) -> None:
        self._driver = driver
        self._geometry = encode_geometry(geometry)
        self._supervisor = supervisor
        self._buffers: dict[int, int] = {}

    def takes_capability(self, operation: int) -> bool:
        return operation == OPERATION_ATTACH

    def handle(self, request: ipc.Received) -> Reply:
        operation = request.message.operation
        if operation == OPERATION_ATTACH:
            return self._attach(request)
        if operation == OPERATION_READ:
            sector, count, offset = decode_transfer(request.message.payload)
            self._driver.read(sector, count, self._buffer_of(request.sender), offset)
        elif operation == OPERATION_WRITE:
            sector, count, offset = decode_transfer(request.message.payload)
            self._driver.write(sector, count, self._buffer_of(request.sender), offset)
        elif operation == OPERATION_FLUSH:
            self._buffer_of(request.sender)
            self._driver.flush()
        elif operation == OPERATION_DETACH:
            self._detach(request.sender)
        elif operation == OPERATION_EVICT:
            self._evict(request)
        else:
            raise KernelError(UNSUPPORTED, "operation is not part of the block service")
        return Reply()

    def stop(self) -> None:
        for client in list(self._buffers):
            self._detach(client)
        self._driver.close()

    def _attach(self, request: ipc.Received) -> Reply:
        buffer = request.transferred
        if buffer == ipc.NO_TRANSFER:
            raise KernelError(INVALID_ARGUMENT, "attach carries no buffer")
        kind, rights, _depth = capabilities.inspect(buffer)
        known = request.sender in self._buffers
        if kind != OBJECT_BUFFER or rights & BUFFER_RIGHTS != BUFFER_RIGHTS:
            capabilities.close(buffer)
            raise KernelError(INVALID_ARGUMENT, "attach needs a readable and writable buffer")
        if not known and len(self._buffers) == MAX_CLIENTS:
            capabilities.close(buffer)
            raise KernelError(LIMIT_EXCEEDED, "the block service has no room for another client")
        self._detach(request.sender)
        self._buffers[request.sender] = buffer
        return Reply(self._geometry)

    def _evict(self, request: ipc.Received) -> None:
        if request.sender != self._supervisor:
            raise KernelError(ACCESS_DENIED, "only the supervisor evicts a client")
        self._detach(decode_client(request.message.payload))

    def _detach(self, client: int) -> None:
        buffer = self._buffers.pop(client, ipc.NO_TRANSFER)
        if buffer != ipc.NO_TRANSFER:
            capabilities.close(buffer)

    def _buffer_of(self, client: int) -> int:
        buffer = self._buffers.get(client, ipc.NO_TRANSFER)
        if buffer == ipc.NO_TRANSFER:
            raise KernelError(BAD_STATE, "the client attached no buffer")
        return buffer
