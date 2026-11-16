from kernel_client import capabilities, services, sockets
from kernel_protocol.configuration.model import NETWORK, Interface
from kernel_protocol.errors.codes import BAD_STATE, KernelError
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.network import OPERATION_EVICT, OPERATION_ROOT, encode_handle
from kernel_protocol.services.network_settings import InterfaceSettings, encode_settings
from kernel_services.manager.devices import DRIVER_RIGHTS
from kernel_services.manager.processes import Launcher, Started
from kernel_services.manager.units.base import ProcessUnit, Unit

NETWORK_PROGRAM = "kernel_services.network.main"
NO_CAPABILITY = 0
NOT_READY = "the network service is not running"


class NetworkUnit(ProcessUnit):
    def __init__(
        self, launcher: Launcher, device: int, entropy: Unit, interface: Interface
    ) -> None:
        super().__init__(NETWORK, NETWORK_PROGRAM, True, launcher)
        self._device = device
        self._entropy = entropy
        self._interface = interface
        self._top = NO_CAPABILITY
        self._accesses: dict[int, tuple[int, int]] = {}
        self.session: sockets.Network | None = None

    def grants(self) -> tuple[tuple[int, int], ...]:
        return ((self._device, DRIVER_RIGHTS), (self._entropy.endpoint(), RIGHT_SEND))

    def role(self) -> bytes:
        interface = self._interface
        return encode_settings(
            InterfaceSettings(interface.address, interface.prefix, interface.gateway, interface.mtu)
        )

    def prepare(self, started: Started) -> None:
        _payload, self._top = services.call(started.endpoint, OPERATION_ROOT)
        self.session = sockets.Network(started.endpoint, self._top)

    def release(self, started: Started) -> None:
        for rights in sorted(self._accesses):
            capabilities.close(self._accesses[rights][1])
        self._accesses = {}
        if self._top != NO_CAPABILITY:
            capabilities.close(self._top)
            self._top = NO_CAPABILITY
        self.session = None

    def evict(self, client: int) -> None:
        if self.started is None:
            return
        try:
            services.call(self.started.endpoint, OPERATION_EVICT, encode_handle(client))
        except KernelError:
            return

    def access(self, rights: int) -> int:
        session = self.session
        if session is None or rights == 0:
            raise KernelError(BAD_STATE, NOT_READY)
        if rights not in self._accesses:
            self._accesses[rights] = session.restrict(rights)
        return self._accesses[rights][1]
