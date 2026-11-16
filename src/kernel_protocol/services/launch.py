from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.processes.status import ARGUMENT_BYTES

HAS_FILES = 0x01
HAS_NETWORK = 0x02
KNOWN_RESOURCES = HAS_FILES | HAS_NETWORK
MAX_COMMAND_BYTES = ARGUMENT_BYTES - 1
REGISTRATION = 0
FIRST_RESOURCE = 1
HANDLES_PER_RESOURCE = 2
SEPARATOR = " "


def encode_launch(resources: int, command: bytes) -> bytes:
    if not command or len(command) > MAX_COMMAND_BYTES or resources & ~KNOWN_RESOURCES:
        raise KernelError(INVALID_ARGUMENT, "a launch names a program within the launch argument")
    return bytes((resources,)) + command


def decode_launch(argument: bytes) -> tuple[int, list[str]]:
    if len(argument) < 2 or argument[0] & ~KNOWN_RESOURCES:
        raise KernelError(INVALID_ARGUMENT, "the process was not started as an application")
    words = [word for word in str(argument[1:], "utf-8").split(SEPARATOR) if word]
    if not words:
        raise KernelError(INVALID_ARGUMENT, "the process was not started as an application")
    return argument[0], words
