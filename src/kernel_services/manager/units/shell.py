from kernel_protocol.configuration.model import SHELL, Access
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_services.manager.clients import Clients
from kernel_services.manager.processes import Launcher, Started
from kernel_services.manager.units.base import ProcessUnit

SHELL_PROGRAM = "kernel_apps.shell.main"


class ShellUnit(ProcessUnit):
    def __init__(self, launcher: Launcher, control: int, clients: Clients, access: Access) -> None:
        super().__init__(SHELL, SHELL_PROGRAM, False, launcher)
        self._control = control
        self._clients = clients
        self._access = access

    def grants(self) -> tuple[tuple[int, int], ...]:
        return ((self._control, RIGHT_SEND),)

    def prepare(self, started: Started) -> None:
        self._clients.admit(started.identity, self._access)

    def release(self, started: Started) -> None:
        self._clients.dismiss(started.identity)
