import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from kernel_tool.network.link import StationLink
from kernel_tool.network.orders import Order
from kernel_tool.outcome import InfrastructureError
from kernel_tool.scenarios.model import Network, Reported
from kernel_tool.toolchain.fetch import sha256_file

EVENT = "event"
STOPPED = "stopped"
CAPTURED = "captured"


@dataclass(frozen=True, slots=True)
class NetworkEvidence:
    peer_stack: str
    capture: str
    capture_sha256: str
    captured_frames: int
    events: tuple[dict[str, object], ...]


class AttachedNetwork:
    def __init__(self, link: StationLink, network: Network, capture: Path) -> None:
        self._link = link
        self._network = network
        self._capture = capture

    @property
    def arguments(self) -> tuple[str, ...]:
        return tuple(self._link.emulator_arguments())

    def obey(self, orders: tuple[Order, ...]) -> None:
        for order in orders:
            self._link.send(order.to_command())

    def finish(self) -> tuple[list[str], NetworkEvidence]:
        self._link.stop()
        events = self._link.events()
        self._capture.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(self._link.capture, self._capture)
        except OSError as error:
            raise InfrastructureError(f"the network station left no capture: {error}") from error
        evidence = NetworkEvidence(
            peer_stack=self._link.stack,
            capture=self._capture.name,
            capture_sha256=sha256_file(self._capture),
            captured_frames=captured_frames(events),
            events=events,
        )
        return missing_reports(self._network.reported, events), evidence


@contextmanager
def attached_network(
    network: Network | None, directory: Path, capture: Path
) -> Iterator[AttachedNetwork | None]:
    if network is None:
        yield None
        return
    with StationLink(directory, network.plan) as link:
        yield AttachedNetwork(link, network, capture)


def captured_frames(events: tuple[dict[str, object], ...]) -> int:
    for event in events:
        frames = event.get(CAPTURED)
        if event.get(EVENT) == STOPPED and isinstance(frames, int):
            return frames
    return 0


def missing_reports(
    reported: tuple[Reported, ...], events: tuple[dict[str, object], ...]
) -> list[str]:
    return [
        f"the network station reported no {expected.event} event with {dict(expected.fields)}"
        for expected in reported
        if not any(_matches(expected, event) for event in events)
    ]


def _matches(expected: Reported, event: dict[str, object]) -> bool:
    return event.get(EVENT) == expected.event and all(
        event.get(key) == value for key, value in expected.fields
    )
