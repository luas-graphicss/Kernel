CONSOLE = "console"
ENTROPY = "entropy"
STORAGE = "storage"
NETWORK = "network"
SHELL = "shell"
SERVICE_NAMES = (CONSOLE, ENTROPY, STORAGE, NETWORK, SHELL)
REQUIRED_SERVICES = (CONSOLE, ENTROPY, STORAGE)
REQUIRED_NEEDS = {
    CONSOLE: (),
    ENTROPY: (),
    STORAGE: (),
    NETWORK: (ENTROPY,),
    SHELL: (CONSOLE, STORAGE),
}
PROCESSES_OF = {CONSOLE: 1, ENTROPY: 1, STORAGE: 3, NETWORK: 1, SHELL: 1}
FILES_NONE = "none"
FILES_READ = "read"
FILES_READ_WRITE = "read-write"
FILES_MODES = (FILES_NONE, FILES_READ, FILES_READ_WRITE)
CONTROL_OBSERVE = 0x01
CONTROL_LAUNCH = 0x02
CONTROL_SIGNAL = 0x04
CONTROL_POWER = 0x08
CONTROL_ALL = 0x0F
CONTROL_NAMES = (
    ("observe", CONTROL_OBSERVE),
    ("launch", CONTROL_LAUNCH),
    ("signal", CONTROL_SIGNAL),
    ("power", CONTROL_POWER),
)
NO_GATEWAY = 0


class Interface:
    def __init__(self, address: int, prefix: int, gateway: int, mtu: int) -> None:
        self.address = address
        self.prefix = prefix
        self.gateway = gateway
        self.mtu = mtu


class ServicePolicy:
    def __init__(
        self,
        name: str,
        needs: tuple[str, ...],
        restarts: int,
        window_nanoseconds: int,
        priority: int,
        heap_bytes: int,
    ) -> None:
        self.name = name
        self.needs = needs
        self.restarts = restarts
        self.window_nanoseconds = window_nanoseconds
        self.priority = priority
        self.heap_bytes = heap_bytes


class Access:
    def __init__(self, network: int, files: str, control: int) -> None:
        self.network = network
        self.files = files
        self.control = control


class Applications:
    def __init__(self, access: Access, limit: int, heap_bytes: int, priority: int) -> None:
        self.access = access
        self.limit = limit
        self.heap_bytes = heap_bytes
        self.priority = priority


class Configuration:
    def __init__(
        self,
        name: str,
        interface: Interface | None,
        services: dict[str, ServicePolicy],
        order: tuple[str, ...],
        shell: Access,
        applications: Applications,
    ) -> None:
        self.name = name
        self.interface = interface
        self.services = services
        self.order = order
        self.shell = shell
        self.applications = applications
