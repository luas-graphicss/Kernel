from kernel_client import devices
from kernel_client.processes import clock, yield_now
from kernel_protocol.devices.layout import SERIAL_TRANSFER_BYTES
from kernel_protocol.errors.codes import TIMED_OUT, KernelError


class SerialPort:
    def __init__(self, device: int) -> None:
        self._device = device

    def write(self, data: bytes, deadline: int) -> int:
        written = 0
        while written < len(data):
            accepted = devices.serial_write(
                self._device, data[written : written + SERIAL_TRANSFER_BYTES]
            )
            written += accepted
            if accepted == 0:
                if clock() >= deadline:
                    break
                yield_now()
        return written

    def read(self, capacity: int, deadline: int) -> bytes:
        try:
            return devices.serial_read(self._device, capacity, deadline)
        except KernelError as error:
            if error.code != TIMED_OUT:
                raise
            return b""
