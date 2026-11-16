from kernel_client import ipc, services
from kernel_client.processes import Startup
from kernel_drivers.virtio_entropy.driver import EntropyDriver
from kernel_protocol.services.lifecycle import decode_supervisor
from kernel_services.entropy.service import EntropyService

REQUEST_TIMEOUT_NANOSECONDS = 2000000000
REGISTRATION = 0
DEVICE = 1


def main() -> bool:
    startup = Startup()
    supervisor, _role = decode_supervisor(startup.argument)
    driver = EntropyDriver(startup.handles[DEVICE], REQUEST_TIMEOUT_NANOSECONDS)
    endpoint = ipc.create_endpoint()
    services.register(startup.handles[REGISTRATION], endpoint)
    return services.serve(endpoint, EntropyService(driver), supervisor)
