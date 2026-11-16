from collections.abc import Callable

from kernel_services.network.ipv4.address import parse_address
from kernel_services.network.ipv4.routing import NO_GATEWAY, checked_route
from kernel_services.network.stack import Stack
from kernel_services.network.tcp.connection import NEVER

PROPAGATION_NANOSECONDS = 1_000_000
MILLISECOND = 1_000_000
SECOND = 1_000_000_000
PREFIX = 24
MTU = 1500

type Fate = Callable[[int, bytes], list[int]]


class Entropy:
    def __init__(self, seed: int) -> None:
        self._state = seed

    def __call__(self, count: int) -> bytes:
        produced = bytearray()
        while len(produced) < count:
            self._state = (self._state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
            produced.extend((self._state >> 32).to_bytes(4, "big"))
        return bytes(produced[:count])


def deliver_once(_sender: int, _frame: bytes) -> list[int]:
    return [PROPAGATION_NANOSECONDS]


def station(index: int, address: str, mtu: int = MTU, gateway: str = "") -> Stack:
    hardware = bytes((0x02, 0, 0, 0, 0, index + 1))
    hop = parse_address(gateway) if gateway else NO_GATEWAY
    route = checked_route(parse_address(address), PREFIX, hop)
    return Stack(hardware, route, mtu, Entropy(index + 1))


class Wire:
    def __init__(self, *stations: Stack) -> None:
        self.stations = stations
        self.now = 0
        self.fate: Fate = deliver_once
        self.carried: list[tuple[int, bytes]] = []
        self._in_transit: list[tuple[int, int, int, bytes]] = []
        self._order = 0

    def inject(self, receiver: int, frame: bytes) -> None:
        self.stations[receiver].frame_arrives(frame, self.now)
        self._collect()

    def settle(self) -> None:
        for stack in self.stations:
            stack.run(self.now)
        self._collect()

    def advance(self, nanoseconds: int) -> None:
        self.run_until(lambda: False, nanoseconds)

    def run_until(
        self, is_done: Callable[[], bool], patience_nanoseconds: int = 60 * SECOND
    ) -> bool:
        limit = self.now + patience_nanoseconds
        self.settle()
        while not is_done():
            moment = self._next_moment()
            if moment > limit:
                self.now = limit
                self.settle()
                return is_done()
            self.now = moment
            self._deliver_due()
            self.settle()
        return True

    def _next_moment(self) -> int:
        moment = NEVER
        for due, _order, _receiver, _frame in self._in_transit:
            moment = min(moment, due)
        for stack in self.stations:
            moment = min(moment, stack.next_deadline(NEVER))
        return max(moment, self.now)

    def _deliver_due(self) -> None:
        due = sorted(entry for entry in self._in_transit if entry[0] <= self.now)
        self._in_transit = [entry for entry in self._in_transit if entry[0] > self.now]
        for _due, _order, receiver, frame in due:
            self.stations[receiver].frame_arrives(frame, self.now)

    def _collect(self) -> None:
        for sender, stack in enumerate(self.stations):
            for frame in stack.take_frames():
                self.carried.append((sender, frame))
                for delay in self.fate(sender, frame):
                    self._schedule(sender, frame, delay)

    def _schedule(self, sender: int, frame: bytes, delay: int) -> None:
        for receiver in range(len(self.stations)):
            if receiver != sender:
                self._order += 1
                self._in_transit.append((self.now + delay, self._order, receiver, frame))
