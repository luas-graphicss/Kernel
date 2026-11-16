from kernel_client import ipc
from kernel_client.services import Reply, Service
from kernel_drivers.virtio_entropy.driver import EntropyDriver
from kernel_protocol.errors.codes import UNSUPPORTED, KernelError
from kernel_protocol.services.entropy import OPERATION_READ, decode_count


class EntropyService(Service):
    def __init__(self, driver: EntropyDriver) -> None:
        self._driver = driver

    def handle(self, request: ipc.Received) -> Reply:
        if request.message.operation != OPERATION_READ:
            raise KernelError(UNSUPPORTED, "operation is not part of the entropy service")
        return Reply(self._driver.read(decode_count(request.message.payload)))

    def stop(self) -> None:
        self._driver.close()
