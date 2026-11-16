from kernel_client import devices
from kernel_client.processes import clock
from kernel_protocol.errors.codes import (
    BAD_STATE,
    IO_ERROR,
    TIMED_OUT,
    UNKNOWN_OUTCOME,
    KernelError,
)

DEVICE_LOST = "the device stopped answering and could not be reset"
NOT_ACCEPTED = "the device was not ready and took no request"
UNCONFIRMED = "the device did not confirm the request before its deadline"


class Transport:
    def __init__(self, device: int, wanted_features: int) -> None:
        self._device = device
        self._wanted_features = wanted_features
        self.failed = False
        self.resets = 0
        self.session = devices.open_session(device, wanted_features)

    def transfer(
        self, segments: tuple[tuple[int, int, int, bool], ...], timeout_nanoseconds: int
    ) -> int:
        if self.failed:
            raise KernelError(IO_ERROR, DEVICE_LOST)
        token = self._submit(segments)
        try:
            return self._await(token, clock() + timeout_nanoseconds)
        except KernelError as error:
            if error.code not in (TIMED_OUT, BAD_STATE):
                raise
        self.recover()
        raise KernelError(UNKNOWN_OUTCOME, UNCONFIRMED)

    def recover(self) -> None:
        self.resets += 1
        try:
            devices.reset(self._device)
            self.session = devices.open_session(self._device, self._wanted_features)
        except KernelError:
            self.failed = True

    def close(self) -> None:
        devices.reset(self._device)

    def _submit(self, segments: tuple[tuple[int, int, int, bool], ...]) -> int:
        try:
            return devices.submit(self._device, segments)
        except KernelError as error:
            if error.code != BAD_STATE:
                raise
        self.recover()
        raise KernelError(IO_ERROR, NOT_ACCEPTED)

    def _await(self, token: int, deadline: int) -> int:
        while True:
            completed, written = devices.wait(self._device, deadline)
            if completed == token:
                return written
