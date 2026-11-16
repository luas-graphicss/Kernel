from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.identity.rights import RIGHT_SEND

REGISTRATION = "registration"
KNOWN_GRANTS = {REGISTRATION: RIGHT_SEND}


class Service:
    def __init__(
        self, program: str, priority: int, heap_bytes: int, grants: tuple[str, ...]
    ) -> None:
        for grant in grants:
            if grant not in KNOWN_GRANTS:
                raise KernelError(INVALID_ARGUMENT, "service asks for an unknown capability")
        self.program = program
        self.priority = priority
        self.heap_bytes = heap_bytes
        self.grants = grants


SERVICES = (Service("kernel_services.echo.main", 2, 0x40000, (REGISTRATION,)),)
