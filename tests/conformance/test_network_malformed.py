import pytest

from doubles.wire import station
from kernel_services.network.counters import NAMES
from kernel_tool.network.malformed import Specimen, Stations, connection_requests, specimens

GUEST = "10.0.2.15"
STATIONS = Stations(
    guest_hardware=station(0, GUEST).interface.hardware,
    guest=bytes((10, 0, 2, 15)),
    sender_hardware=bytes((0x02, 0, 0, 0, 0, 0x77)),
    sender=bytes((10, 0, 2, 77)),
)
SPECIMENS = specimens(STATIONS)


@pytest.mark.parametrize("specimen", SPECIMENS, ids=lambda specimen: specimen.name)
def test_each_malformed_specimen_is_counted_by_its_parser_and_holds_nothing(
    specimen: Specimen,
) -> None:
    stack = station(0, GUEST)
    assert specimen.counter in NAMES

    for frame in specimen.frames:
        stack.frame_arrives(frame, 0)
    stack.run(0)

    assert stack.counters.value(specimen.counter) >= 1
    assert stack.budget.used_bytes == 0
    assert stack.tcp.connection_count() == 0
    assert stack.reassembling() == 0
    assert stack.interface.neighbors.size() == 0


def test_the_whole_corpus_leaves_the_station_able_to_answer() -> None:
    stack = station(0, GUEST)

    for specimen in SPECIMENS:
        for frame in specimen.frames:
            stack.frame_arrives(frame, 0)
    stack.run(0)

    assert {specimen.counter for specimen in SPECIMENS} <= {
        name for name in NAMES if stack.counters.value(name) > 0
    }
    assert stack.budget.used_bytes == 0 and stack.reassembling() == 0


def test_connection_requests_without_a_listener_open_nothing() -> None:
    stack = station(0, GUEST)

    for frame in connection_requests(STATIONS, 8082, 32):
        stack.frame_arrives(frame, 0)
    stack.run(0)

    assert stack.tcp.connection_count() == 0
    assert stack.counters.value("tcp-no-socket") == 32
    assert stack.budget.used_bytes == 0
