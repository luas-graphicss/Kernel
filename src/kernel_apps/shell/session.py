from kernel_client import capabilities, console, files, sockets
from kernel_client.control import Control
from kernel_protocol.configuration.model import CONSOLE, NETWORK, STORAGE
from kernel_protocol.errors.codes import INVALID_HANDLE, PEER_CLOSED, KernelError

WRITE_TIMEOUT_NANOSECONDS = 5000000000
NO_CAPABILITY = 0
LINE_BREAK = "\n"
STALE_CODES = (PEER_CLOSED, INVALID_HANDLE)


class Held:
    def __init__(self, endpoint: int, access: int) -> None:
        self.endpoint = endpoint
        self.access = access

    def close(self) -> None:
        capabilities.close(self.endpoint)
        if self.access != NO_CAPABILITY:
            capabilities.close(self.access)


class Session:
    def __init__(self, control: Control) -> None:
        self.control = control
        self._console = NO_CAPABILITY
        self._files: files.Namespace | None = None
        self._files_held: Held | None = None
        self._network: sockets.Network | None = None
        self._network_held: Held | None = None

    def write(self, text: str) -> None:
        console.write(
            self._terminal(), bytes(text + LINE_BREAK, "utf-8"), WRITE_TIMEOUT_NANOSECONDS
        )

    def write_bytes(self, data: bytes) -> None:
        console.write(self._terminal(), data, WRITE_TIMEOUT_NANOSECONDS)

    def read_line(self) -> str:
        return str(console.read_line(self._terminal()), "utf-8")

    def files(self) -> files.Namespace:
        if self._files is None:
            held = Held(self.control.endpoint_of(STORAGE), self.control.access_to(STORAGE))
            self._files_held = held
            self._files = files.Namespace(held.endpoint, held.access)
        return self._files

    def network(self) -> sockets.Network:
        if self._network is None:
            held = Held(self.control.endpoint_of(NETWORK), self.control.access_to(NETWORK))
            self._network_held = held
            self._network = sockets.Network(held.endpoint, held.access)
        return self._network

    def failed(self, error: KernelError) -> None:
        if error.code in STALE_CODES:
            self.forget()

    def forget(self) -> None:
        if self._files_held is not None:
            self._files_held.close()
        if self._network_held is not None:
            self._network_held.close()
        self._files = None
        self._files_held = None
        self._network = None
        self._network_held = None

    def _terminal(self) -> int:
        if self._console == NO_CAPABILITY:
            self._console = self.control.endpoint_of(CONSOLE)
        return self._console
