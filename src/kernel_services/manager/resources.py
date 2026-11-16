from kernel_protocol.configuration.model import CONSOLE, FILES_NONE, NETWORK, STORAGE, Access
from kernel_protocol.errors.codes import ACCESS_DENIED, BAD_STATE, NOT_FOUND, KernelError
from kernel_services.manager.processes import NO_ENDPOINT
from kernel_services.manager.units.base import Unit
from kernel_services.manager.units.network import NetworkUnit
from kernel_services.manager.units.storage import StorageUnit

UNKNOWN_SERVICE = "no service has this name"
NOT_READY = "the service is not ready"
NOT_GRANTED = "the access policy does not grant this service"


class Resources:
    def __init__(self) -> None:
        self.console: Unit | None = None
        self.storage: StorageUnit | None = None
        self.network: NetworkUnit | None = None

    def may_use(self, service: str, access: Access) -> bool:
        if service == CONSOLE:
            return True
        if service == STORAGE:
            return access.files != FILES_NONE
        if service == NETWORK:
            return access.network != 0
        return False

    def endpoint_of(self, service: str, access: Access) -> int:
        unit = self._unit(service)
        if not self.may_use(service, access):
            raise KernelError(ACCESS_DENIED, NOT_GRANTED)
        if unit is None or unit.endpoint() == NO_ENDPOINT:
            raise KernelError(BAD_STATE, NOT_READY)
        return unit.endpoint()

    def access_to(self, service: str, access: Access) -> int:
        if not self.may_use(service, access):
            raise KernelError(ACCESS_DENIED, NOT_GRANTED)
        if service == STORAGE and self.storage is not None:
            return self.storage.view(access.files)
        if service == NETWORK and self.network is not None:
            return self.network.access(access.network)
        raise KernelError(BAD_STATE, NOT_READY)

    def has_files(self, access: Access) -> bool:
        storage = self.storage
        return access.files != FILES_NONE and storage is not None and storage.namespace is not None

    def has_network(self, access: Access) -> bool:
        network = self.network
        return access.network != 0 and network is not None and network.session is not None

    def evict(self, client: int) -> None:
        if self.storage is not None:
            self.storage.evict(client)
        if self.network is not None:
            self.network.evict(client)

    def _unit(self, service: str) -> Unit | None:
        if service == CONSOLE:
            return self.console
        if service == STORAGE:
            return self.storage
        if service == NETWORK:
            return self.network
        raise KernelError(NOT_FOUND, UNKNOWN_SERVICE)
