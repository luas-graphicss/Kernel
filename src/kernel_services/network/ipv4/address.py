from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError

ADDRESS_BITS = 32
ADDRESS_BYTES = 4
ADDRESS_MASK = 0xFFFFFFFF
UNSPECIFIED = 0
LIMITED_BROADCAST = 0xFFFFFFFF
LOOPBACK_NETWORK = 0x7F000000
LOOPBACK_MASK = 0xFF000000
MULTICAST_NETWORK = 0xE0000000
RESERVED_NETWORK = 0xF0000000
CLASS_MASK = 0xF0000000
OCTET_SEPARATOR = "."
OCTETS = 4
OCTET_LIMIT = 255
OCTET_DIGITS = 3
DIGITS = "0123456789"
MALFORMED = "address is not four decimal octets"


def parse_octet(text: str) -> int:
    if not text or len(text) > OCTET_DIGITS or (len(text) > 1 and text[0] == "0"):
        raise KernelError(INVALID_ARGUMENT, MALFORMED)
    for character in text:
        if character not in DIGITS:
            raise KernelError(INVALID_ARGUMENT, MALFORMED)
    value = int(text)
    if value > OCTET_LIMIT:
        raise KernelError(INVALID_ARGUMENT, MALFORMED)
    return value


def parse_address(text: str) -> int:
    parts = text.split(OCTET_SEPARATOR)
    if len(parts) != OCTETS:
        raise KernelError(INVALID_ARGUMENT, MALFORMED)
    address = 0
    for part in parts:
        address = (address << 8) | parse_octet(part)
    return address


def format_address(address: int) -> str:
    return (
        f"{address >> 24}.{(address >> 16) & OCTET_LIMIT}."
        f"{(address >> 8) & OCTET_LIMIT}.{address & OCTET_LIMIT}"
    )


def prefix_mask(prefix: int) -> int:
    if prefix < 0 or prefix > ADDRESS_BITS:
        raise KernelError(INVALID_ARGUMENT, "prefix length is outside 0 to 32")
    return (ADDRESS_MASK << (ADDRESS_BITS - prefix)) & ADDRESS_MASK


def is_multicast(address: int) -> bool:
    return address & CLASS_MASK == MULTICAST_NETWORK


def is_loopback(address: int) -> bool:
    return address & LOOPBACK_MASK == LOOPBACK_NETWORK


def is_host(address: int) -> bool:
    if address == UNSPECIFIED or address & CLASS_MASK == RESERVED_NETWORK:
        return False
    return not is_multicast(address) and not is_loopback(address)
