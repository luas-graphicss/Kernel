from kernel_apps.shell.session import Session
from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.system.power import POWER_ACTION_RESTART, POWER_ACTION_SHUTDOWN

RESTART = "restart"


def shutdown(session: Session, arguments: list[str]) -> None:
    action = POWER_ACTION_SHUTDOWN
    if arguments:
        if arguments[0] != RESTART or len(arguments) > 1:
            raise KernelError(INVALID_ARGUMENT, "shutdown takes nothing or restart")
        action = POWER_ACTION_RESTART
    session.control.power(action)
    session.write(f"shutdown: action={RESTART if action == POWER_ACTION_RESTART else 'shutdown'}")
