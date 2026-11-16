from kernel_client import services
from kernel_protocol.configuration.model import ServicePolicy
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_services.manager.processes import Launcher, terminate
from kernel_services.manager.units.base import ProcessUnit, Unit
from suites.supervision.protocol import OPERATION_COUNT, STEADY

WORKER = "suites.supervision.worker"
READY_TIMEOUT = 300000000
SECOND = 1000000000
HEAP_BYTES = 0x40000
PRIORITY = 2


class Sequence:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.stopped: list[str] = []


class WorkerUnit(ProcessUnit):
    def __init__(
        self,
        name: str,
        launcher: Launcher,
        sequence: Sequence,
        peers: tuple[Unit, ...] = (),
        behavior: bytes = STEADY,
    ) -> None:
        super().__init__(name, WORKER, True, launcher)
        self.ready_timeout_nanoseconds = READY_TIMEOUT
        self._sequence = sequence
        self._peers = peers
        self._behavior = behavior

    def grants(self) -> tuple[tuple[int, int], ...]:
        return tuple((peer.endpoint(), RIGHT_SEND) for peer in self._peers)

    def role(self) -> bytes:
        return self._behavior

    def start(self, policy: ServicePolicy) -> bool:
        started = super().start(policy)
        if started:
            self._sequence.started.append(self.name)
        return started

    def stop(self) -> bool:
        self._sequence.stopped.append(self.name)
        return super().stop()

    def crash(self) -> None:
        if self.started is not None:
            terminate(self.started.process)

    def count(self) -> int:
        payload, _received = services.call(self.endpoint(), OPERATION_COUNT)
        return payload[0]

    def handles(self) -> int:
        if self.started is None:
            return 0
        return self.started.announcement[0]


def policy(
    name: str, needs: tuple[str, ...], restarts: int, window: int = 60 * SECOND
) -> ServicePolicy:
    return ServicePolicy(name, needs, restarts, window, PRIORITY, HEAP_BYTES)
