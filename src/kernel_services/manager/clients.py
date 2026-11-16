from kernel_protocol.configuration.model import Access
from kernel_protocol.errors.codes import ACCESS_DENIED, KernelError
from kernel_services.manager.resources import Resources

UNKNOWN = "the process holds no admitted control session"
NOT_GRANTED = "the control session does not grant this operation"


class Clients:
    def __init__(self, resources: Resources) -> None:
        self._resources = resources
        self._admitted: dict[int, Access] = {}

    def admit(self, identity: int, access: Access) -> None:
        self._admitted[identity] = access

    def dismiss(self, identity: int) -> None:
        if identity in self._admitted:
            del self._admitted[identity]
        self._resources.evict(identity)

    def access_of(self, identity: int) -> Access:
        access = self._admitted.get(identity)
        if access is None:
            raise KernelError(ACCESS_DENIED, UNKNOWN)
        return access

    def require(self, identity: int, right: int) -> Access:
        access = self.access_of(identity)
        if access.control & right == 0:
            raise KernelError(ACCESS_DENIED, NOT_GRANTED)
        return access
