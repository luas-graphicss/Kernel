from kernel_protocol.errors.codes import LIMIT_EXCEEDED, OK, UNREACHABLE, KernelError
from kernel_services.network.icmp.message import IcmpMessage

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

PENDING = -1
IDENTITY_OFFSET = 4
IDENTITY_BYTES = 4


class Echo:
    def __init__(self, destination: int, identity: int, data: bytes, sent_at: int) -> None:
        self.destination = destination
        self.identity = identity
        self.data = data
        self.sent_at = sent_at
        self.status = PENDING
        self.round_trip_nanoseconds = 0


class EchoTracker:
    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._pending: dict[int, Echo] = {}

    def start(self, destination: int, identity: int, data: bytes, now: int) -> Echo:
        if len(self._pending) == self._capacity or identity in self._pending:
            raise KernelError(LIMIT_EXCEEDED, "too many echo requests are waiting")
        echo = Echo(destination, identity, data, now)
        self._pending[identity] = echo
        return echo

    def cancel(self, echo: Echo) -> None:
        if self._pending.get(echo.identity) is echo:
            del self._pending[echo.identity]

    def reply_arrives(self, source: int, reply: IcmpMessage, now: int) -> None:
        echo = self._pending.get(reply.rest)
        if echo is None or echo.destination != source or echo.data != reply.body:
            return
        echo.round_trip_nanoseconds = now - echo.sent_at
        self._finish(echo, OK)

    def path_reports(self, destination: int, transport: bytes) -> None:
        identity = int.from_bytes(
            transport[IDENTITY_OFFSET : IDENTITY_OFFSET + IDENTITY_BYTES], "big"
        )
        echo = self._pending.get(identity)
        if echo is not None and echo.destination == destination:
            self._finish(echo, UNREACHABLE)

    def hop_unreachable(self, next_hop_of: "Callable[[int], int]", hop: int) -> None:
        for echo in list(self._pending.values()):
            if next_hop_of(echo.destination) == hop:
                self._finish(echo, UNREACHABLE)

    def _finish(self, echo: Echo, status: int) -> None:
        echo.status = status
        del self._pending[echo.identity]
