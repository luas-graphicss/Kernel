from kernel_client import ipc, services
from kernel_client.processes import Startup
from kernel_drivers.uart.port import SerialPort
from kernel_protocol.services.lifecycle import decode_supervisor
from kernel_services.console.service import Console

REGISTRATION = 0
DEVICE = 1


def main() -> bool:
    startup = Startup()
    supervisor, _role = decode_supervisor(startup.argument)
    endpoint = ipc.create_endpoint()
    console = Console(SerialPort(startup.handles[DEVICE]), endpoint, supervisor)
    services.register(startup.handles[REGISTRATION], endpoint)
    return console.run()
