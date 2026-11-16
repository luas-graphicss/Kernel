import random
from collections.abc import Callable

from doubles.wire import MILLISECOND, PROPAGATION_NANOSECONDS, Fate, Wire, station
from kernel_services.network.stack import Stack
from kernel_services.network.tcp.connection import ESTABLISHED, Connection

GUEST = "10.0.2.15"
PEER = "10.0.2.2"
ABSENT = "10.0.2.99"
PORT = 7
BACKLOG = 4
CHUNK_BYTES = 4096
REORDER_NANOSECONDS = 20 * MILLISECOND


def pair(left_mtu: int = 1500, right_mtu: int = 1500) -> tuple[Wire, Stack, Stack]:
    left = station(0, GUEST, left_mtu)
    right = station(1, PEER, right_mtu)
    return Wire(left, right), left, right


def impaired(seed: int, loss: float, duplicate: float, reorder: float) -> Fate:
    chooser = random.Random(seed)

    def fate(_sender: int, _frame: bytes) -> list[int]:
        if chooser.random() < loss:
            return []
        delay = PROPAGATION_NANOSECONDS
        if chooser.random() < reorder:
            delay += int(chooser.random() * REORDER_NANOSECONDS)
        if chooser.random() < duplicate:
            return [delay, delay + int(chooser.random() * REORDER_NANOSECONDS)]
        return [delay]

    return fate


def silence_from(silenced: int) -> Fate:
    def fate(sender: int, _frame: bytes) -> list[int]:
        return [] if sender == silenced else [PROPAGATION_NANOSECONDS]

    return fate


def connect(
    wire: Wire, client: Stack, server: Stack, port: int = PORT
) -> tuple[Connection, Connection]:
    listener = server.tcp.listen(port, BACKLOG)
    opened = client.tcp.connect(server.interface.route.address, port, wire.now)
    wire.settle()
    assert wire.run_until(lambda: opened.state == ESTABLISHED and len(listener.ready) == 1)
    accepted = listener.accept()
    assert accepted is not None
    return opened, accepted


def carry(
    wire: Wire, sender: Connection, receiver: Connection, data: bytes, patience: int
) -> bytes:
    received = bytearray()
    written = 0

    def moved() -> bool:
        nonlocal written
        if written < len(data):
            written += sender.write(data[written : written + CHUNK_BYTES], wire.now)
        received.extend(receiver.read(len(data)))
        wire.settle()
        return len(received) >= len(data)

    assert wire.run_until(moved, patience), f"{len(received)} of {len(data)} bytes arrived"
    return bytes(received)


def until(wire: Wire, condition: Callable[[], bool], patience: int) -> bool:
    def settled() -> bool:
        wire.settle()
        return condition()

    return wire.run_until(settled, patience)
