from kernel_services.manager.devices import DRIVER_RIGHTS
from kernel_services.manager.processes import Launcher
from kernel_services.manager.units.base import ProcessUnit

CONSOLE_PROGRAM = "kernel_services.console.main"
ENTROPY_PROGRAM = "kernel_services.entropy.main"


class DriverUnit(ProcessUnit):
    def __init__(self, name: str, module: str, launcher: Launcher, device: int) -> None:
        super().__init__(name, module, True, launcher)
        self._device = device

    def grants(self) -> tuple[tuple[int, int], ...]:
        return ((self._device, DRIVER_RIGHTS),)
