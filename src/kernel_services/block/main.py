from kernel_client import ipc, services
from kernel_client.processes import Startup
from kernel_drivers.virtio_block.driver import BlockDriver
from kernel_protocol.services.lifecycle import decode_supervisor
from kernel_services.block.service import BlockService, geometry_of

REQUEST_TIMEOUT_NANOSECONDS = 5000000000
REGISTRATION = 0
DEVICE = 1


def main() -> bool:
    startup = Startup()
    supervisor, _role = decode_supervisor(startup.argument)
    driver = BlockDriver(startup.handles[DEVICE], REQUEST_TIMEOUT_NANOSECONDS)
    geometry = geometry_of(driver, startup.identity)
    endpoint = ipc.create_endpoint()
    services.register(startup.handles[REGISTRATION], endpoint, geometry.identity)
    return services.serve(endpoint, BlockService(driver, geometry, supervisor), supervisor)
