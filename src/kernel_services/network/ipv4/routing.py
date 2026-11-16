from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_services.network.ipv4.address import (
    ADDRESS_MASK,
    LIMITED_BROADCAST,
    is_host,
    prefix_mask,
)

NO_GATEWAY = 0
SHORTEST_PREFIX = 8
LONGEST_PREFIX = 30


class Route:
    def __init__(self, address: int, prefix: int, gateway: int) -> None:
        self.address = address
        self.prefix = prefix
        self.mask = prefix_mask(prefix)
        self.network = address & self.mask
        self.broadcast = self.network | (~self.mask & ADDRESS_MASK)
        self.gateway = gateway

    def is_on_link(self, destination: int) -> bool:
        return destination & self.mask == self.network

    def is_broadcast(self, destination: int) -> bool:
        return destination == LIMITED_BROADCAST or destination == self.broadcast

    def names_a_station(self, address: int) -> bool:
        return is_host(address) and address != self.network and address != self.broadcast

    def next_hop(self, destination: int) -> int:
        if self.is_on_link(destination):
            return destination
        return self.gateway


def checked_route(address: int, prefix: int, gateway: int) -> Route:
    if prefix < SHORTEST_PREFIX or prefix > LONGEST_PREFIX:
        raise KernelError(INVALID_ARGUMENT, "prefix length is outside 8 to 30")
    route = Route(address, prefix, gateway)
    if not route.names_a_station(address):
        raise KernelError(INVALID_ARGUMENT, "interface address is not a station of its network")
    if gateway == NO_GATEWAY:
        return route
    if gateway == address or not route.is_on_link(gateway) or not route.names_a_station(gateway):
        raise KernelError(INVALID_ARGUMENT, "gateway is not another station of the network")
    return route
