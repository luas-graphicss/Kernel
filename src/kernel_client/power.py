from kernel_client.calls import scalar
from kernel_protocol.syscalls.numbers import SYSTEM_POWER
from kernel_protocol.system.power import POWER_ACTION_RESTART, POWER_ACTION_SHUTDOWN


def request_shutdown(system: int) -> None:
    scalar(SYSTEM_POWER, system, POWER_ACTION_SHUTDOWN)


def request_restart(system: int) -> None:
    scalar(SYSTEM_POWER, system, POWER_ACTION_RESTART)
