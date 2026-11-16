from kernel_apps import runtime
from kernel_client import services
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import KernelError, error_name
from kernel_protocol.services.launch import REGISTRATION, decode_launch
from kernel_protocol.services.lifecycle import OPERATION_REGISTER

ENTRY = "main"
MODULE_NAME = "__main__"


def execute(source: bytes) -> bool:
    scope: dict[str, object] = {"__name__": MODULE_NAME}
    exec(source, scope)
    entry = scope.get(ENTRY)
    if not callable(entry):
        return True
    return entry() is not False


def main() -> bool:
    startup = Startup()
    resources, arguments = decode_launch(startup.argument)
    services.note(startup.handles[REGISTRATION], OPERATION_REGISTER)
    application = runtime.install(startup.handles, resources, arguments)
    try:
        source = application.read_program()
    except KernelError as error:
        print(f"application: program={arguments[0]} error={error_name(error.code)}")
        return False
    return execute(source)
