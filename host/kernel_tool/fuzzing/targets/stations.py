from collections.abc import Callable

from kernel_services.network.ipv4.address import parse_address
from kernel_services.network.ipv4.routing import NO_GATEWAY, checked_route
from kernel_services.network.stack import Stack
from kernel_services.network.tcp.connection import NEVER

GUEST_ADDRESS = parse_address("10.0.2.15")
PEER_ADDRESS = parse_address("10.0.2.2")
GUEST_HARDWARE = bytes((0x02, 0, 0, 0, 0, 0x01))
PEER_HARDWARE = bytes((0x02, 0, 0, 0, 0, 0x02))
PREFIX = 24
MTU = 1500
MILLISECOND = 1_000_000
SECOND = 1_000_000_000
PROPAGATION_NANOSECONDS = MILLISECOND
MULTIPLIER = 6364136223846793005
INCREMENT = 1442695040888963407
STATE_MODULUS = 1 << 64
WORD_BYTES = 4
GUEST = 0
PEER = 1

type Fate = Callable[[int, bytes], list[tuple[int, bytes]]]


class RepeatableEntropy:
    def __init__(self, seed: int) -> None:
        self._state = seed

    def __call__(self, count: int) -> bytes:
        produced = bytearray()
        while len(produced) < count:
            self._state = (self._state * MULTIPLIER + INCREMENT) % STATE_MODULUS
            produced.extend((self._state >> 32).to_bytes(WORD_BYTES, "big"))
        return bytes(produced[:count])


def guest_station() -> Stack:
    route = checked_route(GUEST_ADDRESS, PREFIX, NO_GATEWAY)
    return Stack(GUEST_HARDWARE, route, MTU, RepeatableEntropy(GUEST + 1))


def peer_station() -> Stack:
    route = checked_route(PEER_ADDRESS, PREFIX, NO_GATEWAY)
    return Stack(PEER_HARDWARE, route, MTU, RepeatableEntropy(PEER + 1))


def deliver_unchanged(_sender: int, frame: bytes) -> list[tuple[int, bytes]]:
    return [(PROPAGATION_NANOSECONDS, frame)]


class Link:
    def __init__(self, guest: Stack, peer: Stack, fate: Fate = deliver_unchanged) -> None:
        self.stations = (guest, peer)
        self.now = 0
        self.delivered_to_guest: list[bytes] = []
        self._fate = fate
        self._in_transit: list[tuple[int, int, int, bytes]] = []
        self._order = 0

    def settle(self) -> None:
        for sender, stack in enumerate(self.stations):
            stack.run(self.now)
            for frame in stack.take_frames():
                for delay, carried in self._fate(sender, frame):
                    self._order += 1
                    self._in_transit.append((self.now + delay, self._order, 1 - sender, carried))

    def run_until(self, is_done: Callable[[], bool], patience_nanoseconds: int) -> bool:
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
            if receiver == GUEST:
                self.delivered_to_guest.append(frame)
            self.stations[receiver].frame_arrives(frame, self.now)
