from kernel_client.processes import Startup
from kernel_services.manager.journal import report
from kernel_services.manager.system import System

SYSTEM = 0


def main() -> bool:
    startup = Startup()
    report("manager=started runtime=micropython privilege=user")
    return System(startup.handles[SYSTEM], startup.identity).run()
