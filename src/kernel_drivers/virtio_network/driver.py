from kernel_client import capabilities, devices, memory
from kernel_protocol.devices.layout import DEVICE_REQUESTS
from kernel_protocol.errors.codes import (
    BAD_STATE,
    IO_ERROR,
    LIMIT_EXCEEDED,
    TIMED_OUT,
    UNSUPPORTED,
    KernelError,
)

VIRTIO_MODEL = 1
FEATURE_HARDWARE_ADDRESS = 1 << 5
FEATURE_LINK_STATUS = 1 << 16
WANTED_FEATURES = FEATURE_HARDWARE_ADDRESS | FEATURE_LINK_STATUS
RECEIVE_QUEUE = 0
TRANSMIT_QUEUE = 1
QUEUES = 2
HEADER_BYTES = 12
HEADER = bytes(HEADER_BYTES)
SLOT_BYTES = 2048
MAXIMUM_FRAME_BYTES = 1514
RECEIVE_SLOTS = DEVICE_REQUESTS
TRANSMIT_SLOTS = DEVICE_REQUESTS
HARDWARE_ADDRESS_OFFSET = 0
HARDWARE_ADDRESS_BYTES = 6
LINK_STATUS_OFFSET = 6
LINK_STATUS_BYTES = 2
LINK_UP = 0x1
DEVICE_LOST_CODES = (BAD_STATE, IO_ERROR)
TRANSMITTED = b""


class NetworkDriver:
    def __init__(self, device: int) -> None:
        self._device = device
        self._buffer = memory.create_buffer((RECEIVE_SLOTS + TRANSMIT_SLOTS) * SLOT_BYTES)
        self._mapping = memory.Mapping(self._buffer, True)
        self._receiving: dict[int, int] = {}
        self._transmitting: dict[int, int] = {}
        self._free_transmit_slots: list[int] = []
        self._reports_link = False
        self.hardware = b""
        self.resets = 0
        self.has_failed = False
        try:
            self._start()
        except KernelError:
            self._release()
            raise

    def can_transmit(self) -> bool:
        return not self.has_failed and len(self._free_transmit_slots) != 0

    def transmit(self, frame: bytes) -> bool:
        if not self.can_transmit() or len(frame) > MAXIMUM_FRAME_BYTES:
            return False
        slot = self._free_transmit_slots.pop()
        offset = slot * SLOT_BYTES
        self._mapping.write(offset, HEADER + frame)
        segment = (self._buffer, offset, HEADER_BYTES + len(frame), False)
        try:
            token = devices.submit(self._device, (segment,), TRANSMIT_QUEUE)
        except KernelError as error:
            self._free_transmit_slots.append(slot)
            if error.code == LIMIT_EXCEEDED:
                return False
            self._lost(error)
            return False
        self._transmitting[token] = slot
        return True

    def wait(self, deadline: int) -> bytes | None:
        if self.has_failed:
            return None
        try:
            token, written = devices.wait(self._device, deadline)
        except KernelError as error:
            if error.code != TIMED_OUT:
                self._lost(error)
            return None
        slot = self._transmitting.pop(token, None)
        if slot is not None:
            self._free_transmit_slots.append(slot)
            return TRANSMITTED
        slot = self._receiving.pop(token, None)
        if slot is None:
            return TRANSMITTED
        frame = b""
        if written > HEADER_BYTES:
            frame = self._mapping.read(slot * SLOT_BYTES + HEADER_BYTES, written - HEADER_BYTES)
        self._post(slot)
        return frame

    def is_linked(self) -> bool:
        if self.has_failed:
            return False
        if not self._reports_link:
            return True
        try:
            status = devices.read_config(self._device, LINK_STATUS_OFFSET, LINK_STATUS_BYTES)
        except KernelError as error:
            self._lost(error)
            return False
        return status[0] & LINK_UP != 0

    def recover(self) -> bool:
        self.resets += 1
        try:
            devices.reset(self._device)
            self._start()
        except KernelError:
            self.has_failed = True
            return False
        self.has_failed = False
        return True

    def close(self) -> None:
        try:
            devices.reset(self._device)
        except KernelError as error:
            if error.code not in DEVICE_LOST_CODES:
                raise
        self._release()

    def _start(self) -> None:
        session = devices.open_session(self._device, WANTED_FEATURES)
        if session.features & FEATURE_HARDWARE_ADDRESS == 0 or session.queues < QUEUES:
            raise KernelError(UNSUPPORTED, "the device offers no address or no transmit queue")
        self._reports_link = session.features & FEATURE_LINK_STATUS != 0
        self.hardware = devices.read_config(
            self._device, HARDWARE_ADDRESS_OFFSET, HARDWARE_ADDRESS_BYTES
        )
        self._receiving = {}
        self._transmitting = {}
        self._free_transmit_slots = list(range(RECEIVE_SLOTS, RECEIVE_SLOTS + TRANSMIT_SLOTS))
        for slot in range(RECEIVE_SLOTS):
            self._post(slot)

    def _post(self, slot: int) -> None:
        segment = (self._buffer, slot * SLOT_BYTES, SLOT_BYTES, True)
        try:
            self._receiving[devices.submit(self._device, (segment,), RECEIVE_QUEUE)] = slot
        except KernelError as error:
            self._lost(error)

    def _lost(self, error: KernelError) -> None:
        if error.code not in DEVICE_LOST_CODES:
            raise error
        self.has_failed = True

    def _release(self) -> None:
        self._mapping.unmap()
        capabilities.close(self._buffer)
