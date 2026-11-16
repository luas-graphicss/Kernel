from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.identity.rights import RIGHTS_ALL
from kernel_protocol.processes.status import ARGUMENT_BYTES, GRANTS, NAME_BYTES, PRIORITY_LEVELS

REQUEST_VERSION = 1
REQUEST_BYTES = 296
PAGE_BYTES = 4096
NAME_CHARACTERS = "abcdefghijklmnopqrstuvwxyz0123456789_"
NAME_SEPARATOR = "."


def name_is_valid(name: str) -> bool:
    if not name or len(name) > NAME_BYTES:
        return False
    for part in name.split(NAME_SEPARATOR):
        if not part:
            return False
        for character in part:
            if character not in NAME_CHARACTERS:
                return False
    return True


def pack_unsigned(value: int, width: int) -> bytes:
    return value.to_bytes(width, "little")


def encode_grants(grants: tuple[tuple[int, int], ...]) -> bytes:
    if len(grants) > GRANTS:
        raise KernelError(INVALID_ARGUMENT, "too many granted capabilities")
    encoded = b""
    for handle, rights in grants:
        if handle <= 0 or rights <= 0 or rights & ~RIGHTS_ALL:
            raise KernelError(INVALID_ARGUMENT, "grant names no handle or no valid right")
        encoded += pack_unsigned(handle, 8) + pack_unsigned(rights, 8)
    return encoded + bytes(16 * (GRANTS - len(grants)))


def encode_spawn_request(
    name: str,
    argument: bytes,
    priority: int,
    heap_bytes: int,
    memory_bytes: int,
    grants: tuple[tuple[int, int], ...],
) -> bytes:
    if not name_is_valid(name):
        raise KernelError(INVALID_ARGUMENT, "program name is not a module path")
    if len(argument) > ARGUMENT_BYTES:
        raise KernelError(INVALID_ARGUMENT, "argument exceeds its field")
    if priority < 0 or priority >= PRIORITY_LEVELS:
        raise KernelError(INVALID_ARGUMENT, "priority out of range")
    if heap_bytes < 0 or heap_bytes % PAGE_BYTES or memory_bytes < 0 or memory_bytes % PAGE_BYTES:
        raise KernelError(INVALID_ARGUMENT, "sizes must be whole pages")
    encoded_name = bytes(name, "utf-8")
    return (
        pack_unsigned(REQUEST_VERSION, 4)
        + pack_unsigned(priority, 4)
        + pack_unsigned(heap_bytes, 8)
        + pack_unsigned(memory_bytes, 8)
        + pack_unsigned(len(encoded_name), 4)
        + pack_unsigned(len(argument), 4)
        + pack_unsigned(len(grants), 4)
        + bytes(4)
        + encode_grants(grants)
        + encoded_name
        + bytes(NAME_BYTES - len(encoded_name))
        + argument
        + bytes(ARGUMENT_BYTES - len(argument))
    )
