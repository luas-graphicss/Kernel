from kernel_protocol.configuration.errors import (
    GATEWAY_OFF_LINK,
    INVALID_ADDRESS,
    MISSING_DEPENDENCY,
    MISSING_SECTION,
    MISSING_SERVICE,
    OUT_OF_RANGE,
    PROCESS_BUDGET,
    SELF_DEPENDENCY,
    UNKNOWN_DEPENDENCY,
    UNKNOWN_RIGHT,
    UNKNOWN_SECTION,
    UNKNOWN_SERVICE,
    UNSUPPORTED_VERSION,
    ConfigurationError,
)
from kernel_protocol.configuration.fields import Section
from kernel_protocol.configuration.graph import start_order
from kernel_protocol.configuration.model import (
    CONTROL_NAMES,
    FILES_MODES,
    FILES_NONE,
    NETWORK,
    NO_GATEWAY,
    PROCESSES_OF,
    REQUIRED_NEEDS,
    REQUIRED_SERVICES,
    SERVICE_NAMES,
    Access,
    Applications,
    Configuration,
    Interface,
    ServicePolicy,
)
from kernel_protocol.configuration.syntax import parse_document
from kernel_protocol.services.network import ACCESS_NAMES

FORMAT_VERSION = 1
SYSTEM_SECTION = "system"
INTERFACE_SECTION = "interface"
SERVICE_PREFIX = "service."
SHELL_ACCESS_SECTION = "access.shell"
APPLICATION_ACCESS_SECTION = "access.application"
MAX_NAME_BYTES = 32
MAX_RESTARTS = 16
MAX_WINDOW_SECONDS = 3600
NANOSECONDS_PER_SECOND = 1000000000
PRIORITY_LEVELS = 4
DEFAULT_PRIORITY = 2
PAGE_BYTES = 4096
DEFAULT_HEAP_BYTES = 0x100000
MAX_HEAP_BYTES = 0x400000
MAX_APPLICATIONS = 8
SHORTEST_PREFIX = 8
LONGEST_PREFIX = 30
SMALLEST_MTU = 576
LARGEST_MTU = 1500
ADDRESS_BITS = 32
ADDRESS_MASK = 0xFFFFFFFF
OCTETS = 4
OCTET_LIMIT = 255
OCTET_DIGITS = 3
DIGITS = "0123456789"
SUPERVISOR_PROCESSES = 1


class Limits:
    def __init__(self, processes: int) -> None:
        self.processes = processes


def parse_address(text: str, where: str) -> int:
    parts = text.split(".")
    if len(parts) != OCTETS:
        raise ConfigurationError(INVALID_ADDRESS, where)
    address = 0
    for part in parts:
        if not part or len(part) > OCTET_DIGITS:
            raise ConfigurationError(INVALID_ADDRESS, where)
        for character in part:
            if character not in DIGITS:
                raise ConfigurationError(INVALID_ADDRESS, where)
        octet = int(part)
        if octet > OCTET_LIMIT:
            raise ConfigurationError(INVALID_ADDRESS, where)
        address = (address << 8) | octet
    return address


def network_of(address: int, prefix: int) -> int:
    mask = (ADDRESS_MASK << (ADDRESS_BITS - prefix)) & ADDRESS_MASK
    return address & mask


def names_a_station(address: int, prefix: int) -> bool:
    host_mask = ADDRESS_MASK >> prefix
    host = address & host_mask
    return host != 0 and host != host_mask


def read_interface(section: Section) -> Interface:
    where = section.name
    prefix = section.number("prefix", SHORTEST_PREFIX, LONGEST_PREFIX)
    address = parse_address(section.text("address"), where + ".address")
    if not names_a_station(address, prefix):
        raise ConfigurationError(INVALID_ADDRESS, where + ".address")
    gateway = NO_GATEWAY
    gateway_text = section.text_or("gateway", "")
    if gateway_text:
        gateway = parse_address(gateway_text, where + ".gateway")
        on_link = network_of(gateway, prefix) == network_of(address, prefix)
        if not on_link or gateway == address or not names_a_station(gateway, prefix):
            raise ConfigurationError(GATEWAY_OFF_LINK, where + ".gateway")
    mtu = section.number("mtu", SMALLEST_MTU, LARGEST_MTU)
    section.finish()
    return Interface(address, prefix, gateway, mtu)


def read_heap(section: Section, default: int) -> int:
    heap_bytes = section.number_or("heap_bytes", PAGE_BYTES, MAX_HEAP_BYTES, default)
    if heap_bytes % PAGE_BYTES:
        raise ConfigurationError(OUT_OF_RANGE, section.name + ".heap_bytes")
    return heap_bytes


def read_service(name: str, section: Section) -> ServicePolicy:
    needs = tuple(section.texts_or_none("needs"))
    policy = ServicePolicy(
        name,
        needs,
        section.number("restarts", 0, MAX_RESTARTS),
        section.number("window_seconds", 1, MAX_WINDOW_SECONDS) * NANOSECONDS_PER_SECOND,
        section.number_or("priority", 0, PRIORITY_LEVELS - 1, DEFAULT_PRIORITY),
        read_heap(section, DEFAULT_HEAP_BYTES),
    )
    section.finish()
    return policy


def rights_from(names: list[str], known: tuple[tuple[str, int], ...], where: str) -> int:
    rights = 0
    for name in names:
        granted = 0
        for candidate, right in known:
            if candidate == name:
                granted = right
        if granted == 0:
            raise ConfigurationError(UNKNOWN_RIGHT, where)
        rights |= granted
    return rights


def read_access(section: Section, has_control: bool) -> Access:
    where = section.name
    network = rights_from(section.texts_or_none("network"), ACCESS_NAMES, where + ".network")
    files = section.text_or("files", FILES_NONE)
    if files not in FILES_MODES:
        raise ConfigurationError(OUT_OF_RANGE, where + ".files")
    control = 0
    if has_control:
        control = rights_from(section.texts_or_none("control"), CONTROL_NAMES, where + ".control")
    return Access(network, files, control)


def read_applications(section: Section) -> Applications:
    access = read_access(section, False)
    applications = Applications(
        access,
        section.number_or("limit", 0, MAX_APPLICATIONS, 0),
        read_heap(section, DEFAULT_HEAP_BYTES),
        section.number_or("priority", 0, PRIORITY_LEVELS - 1, DEFAULT_PRIORITY),
    )
    section.finish()
    return applications


def check_dependencies(services: dict[str, ServicePolicy]) -> tuple[str, ...]:
    for name in REQUIRED_SERVICES:
        if name not in services:
            raise ConfigurationError(MISSING_SERVICE, name)
    needs: dict[str, tuple[str, ...]] = {}
    for name in sorted(services):
        policy = services[name]
        for need in policy.needs:
            if need == name:
                raise ConfigurationError(SELF_DEPENDENCY, name)
            if need not in services:
                raise ConfigurationError(UNKNOWN_DEPENDENCY, f"{name}.{need}")
        for required in REQUIRED_NEEDS[name]:
            if required not in policy.needs:
                raise ConfigurationError(MISSING_DEPENDENCY, f"{name}.{required}")
        needs[name] = policy.needs
    return start_order(needs)


def check_budget(
    services: dict[str, ServicePolicy], applications: Applications, limits: Limits
) -> None:
    processes = SUPERVISOR_PROCESSES + applications.limit
    for name in services:
        processes += PROCESSES_OF[name]
    if processes > limits.processes:
        raise ConfigurationError(PROCESS_BUDGET, str(processes))


def section_of(document: dict[str, dict[str, object]], name: str) -> Section:
    if name not in document:
        raise ConfigurationError(MISSING_SECTION, name)
    return Section(name, document[name])


def read_system(section: Section) -> str:
    if section.number("version", 0, FORMAT_VERSION + 1) != FORMAT_VERSION:
        raise ConfigurationError(UNSUPPORTED_VERSION, section.name + ".version")
    name = section.text("name")
    if not name or len(name) > MAX_NAME_BYTES:
        raise ConfigurationError(OUT_OF_RANGE, section.name + ".name")
    section.finish()
    return name


def validate(document: dict[str, dict[str, object]], limits: Limits) -> Configuration:
    known = [SYSTEM_SECTION, INTERFACE_SECTION, SHELL_ACCESS_SECTION, APPLICATION_ACCESS_SECTION]
    services: dict[str, ServicePolicy] = {}
    for section_name in sorted(document):
        if section_name.startswith(SERVICE_PREFIX):
            service = section_name[len(SERVICE_PREFIX) :]
            if service not in SERVICE_NAMES:
                raise ConfigurationError(UNKNOWN_SERVICE, service)
            services[service] = read_service(service, Section(section_name, document[section_name]))
        elif section_name not in known:
            raise ConfigurationError(UNKNOWN_SECTION, section_name)
    name = read_system(section_of(document, SYSTEM_SECTION))
    order = check_dependencies(services)
    interface = None
    if NETWORK in services:
        interface = read_interface(section_of(document, INTERFACE_SECTION))
    elif INTERFACE_SECTION in document:
        raise ConfigurationError(MISSING_SERVICE, NETWORK)
    shell_section = section_of(document, SHELL_ACCESS_SECTION)
    shell = read_access(shell_section, True)
    shell_section.finish()
    applications = read_applications(section_of(document, APPLICATION_ACCESS_SECTION))
    check_budget(services, applications, limits)
    return Configuration(name, interface, services, order, shell, applications)


def load(text: str, limits: Limits) -> Configuration:
    return validate(parse_document(text), limits)
