from kernel_client import files, sockets
from kernel_protocol.errors.codes import BAD_STATE, INVALID_ARGUMENT, KernelError
from kernel_protocol.services.files import OPEN_READ
from kernel_protocol.services.launch import FIRST_RESOURCE, HAS_FILES, HAS_NETWORK

MAX_PROGRAM_BYTES = 65536
NOT_AN_APPLICATION = "the process was not started as an application"


class Application:
    def __init__(
        self,
        arguments: list[str],
        namespace: files.Namespace | None,
        network: sockets.Network | None,
    ) -> None:
        self.arguments = arguments
        self.files = namespace
        self.network = network

    def read_program(self) -> bytes:
        namespace = self.files
        if namespace is None:
            raise KernelError(BAD_STATE, "the application was started without files")
        program = namespace.open(bytes(self.arguments[0], "utf-8"), OPEN_READ)
        try:
            if program.size > MAX_PROGRAM_BYTES:
                raise KernelError(INVALID_ARGUMENT, "the program exceeds the size of a program")
            return program.read(0, program.size)
        finally:
            program.close()


class Holder:
    def __init__(self) -> None:
        self.application: Application | None = None


_holder = Holder()


def install(handles: tuple[int, ...], resources: int, arguments: list[str]) -> Application:
    position = FIRST_RESOURCE
    namespace = None
    network = None
    if resources & HAS_FILES:
        namespace = files.Namespace(handles[position], handles[position + 1])
        position += 2
    if resources & HAS_NETWORK:
        network = sockets.Network(handles[position], handles[position + 1])
    _holder.application = Application(arguments, namespace, network)
    return _holder.application


def current() -> Application:
    application = _holder.application
    if application is None:
        raise KernelError(BAD_STATE, NOT_AN_APPLICATION)
    return application
