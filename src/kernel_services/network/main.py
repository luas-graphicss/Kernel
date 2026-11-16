from kernel_client import ipc, services
from kernel_client.processes import Startup
from kernel_drivers.virtio_network.driver import NetworkDriver
from kernel_protocol.services.lifecycle import decode_supervisor
from kernel_protocol.services.network_settings import decode_settings
from kernel_services.network.entropy import EntropyPool
from kernel_services.network.ipv4.address import format_address
from kernel_services.network.ipv4.routing import checked_route
from kernel_services.network.link import Link
from kernel_services.network.service import NetworkService
from kernel_services.network.stack import Stack

REGISTRATION = 0
DEVICE = 1
ENTROPY = 2


def main() -> bool:
    startup = Startup()
    supervisor, role = decode_supervisor(startup.argument)
    settings = decode_settings(role)
    route = checked_route(settings.address, settings.prefix, settings.gateway)
    link = Link(NetworkDriver(startup.handles[DEVICE]))
    pool = EntropyPool(startup.handles[ENTROPY])
    stack = Stack(link.hardware(), route, settings.mtu, pool.take)
    endpoint = ipc.create_endpoint()
    service = NetworkService(stack, link, endpoint, startup.identity, supervisor)
    address = format_address(route.address)
    print(f"network: interface={address}/{route.prefix} mtu={settings.mtu}")
    services.register(startup.handles[REGISTRATION], endpoint)
    return service.run()
