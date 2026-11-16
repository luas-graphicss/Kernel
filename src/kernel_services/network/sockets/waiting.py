from kernel_client import ipc, services
from kernel_client.services import Reply
from kernel_protocol.errors.codes import (
    CANCELLED,
    LIMIT_EXCEEDED,
    PEER_CLOSED,
    TIMED_OUT,
    KernelError,
)
from kernel_protocol.services.network import NO_WAIT, WAIT_FOREVER
from kernel_services.network.sockets.registry import Session, Socket

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable

MAX_WAITERS = 64
NEVER = 1 << 62


class Completion:
    def __init__(
        self,
        reply: Reply,
        commit: "Callable[[], object] | None" = None,
        undo: "Callable[[], object] | None" = None,
    ) -> None:
        self.reply = reply
        self.commit = commit
        self.undo = undo


class Waiter:
    def __init__(
        self,
        request: ipc.Received,
        session: Session,
        socket: Socket | None,
        deadline: int,
        attempt: "Callable[[], Completion | None]",
        abandon: "Callable[[], object] | None",
    ) -> None:
        self.request = request
        self.session = session
        self.socket = socket
        self.deadline = deadline
        self.attempt = attempt
        self.abandon = abandon

    def operation(self) -> int:
        return self.request.message.operation


def deliver(request: ipc.Received, completion: Completion) -> None:
    try:
        ipc.answer(request, completion.reply.payload, completion.reply.transfer)
    except KernelError as error:
        if error.code != PEER_CLOSED:
            raise
        if completion.undo is not None:
            completion.undo()
        return
    if completion.commit is not None:
        completion.commit()


class WaitList:
    def __init__(self) -> None:
        self._waiters: list[Waiter] = []

    def count(self) -> int:
        return len(self._waiters)

    def answer(
        self,
        request: ipc.Received,
        session: Session,
        socket: Socket | None,
        timeout_nanoseconds: int,
        now: int,
        attempt: "Callable[[], Completion | None]",
        abandon: "Callable[[], object] | None" = None,
    ) -> None:
        deadline = NEVER if timeout_nanoseconds == WAIT_FOREVER else now + timeout_nanoseconds
        waiter = Waiter(request, session, socket, deadline, attempt, abandon)
        self._supersede(waiter)
        if self._try(waiter):
            return
        if timeout_nanoseconds == NO_WAIT:
            self._give_up(waiter, TIMED_OUT)
        elif len(self._waiters) == MAX_WAITERS:
            self._give_up(waiter, LIMIT_EXCEEDED)
        else:
            self._waiters.append(waiter)

    def settle(self, now: int) -> None:
        for waiter in list(self._waiters):
            if waiter not in self._waiters:
                continue
            if self._try(waiter):
                self._waiters.remove(waiter)
            elif waiter.deadline <= now:
                self._waiters.remove(waiter)
                self._give_up(waiter, TIMED_OUT)

    def next_deadline(self, none: int) -> int:
        deadline = none
        for waiter in self._waiters:
            if waiter.deadline < deadline:
                deadline = waiter.deadline
        return deadline

    def cancel_socket(self, socket: Socket) -> None:
        self._cancel([held for held in self._waiters if held.socket is socket])

    def cancel_session(self, session: Session) -> None:
        self._cancel([held for held in self._waiters if held.session is session])

    def cancel_all(self) -> None:
        self._cancel(list(self._waiters))

    def _supersede(self, waiter: Waiter) -> None:
        self._cancel(
            [
                held
                for held in self._waiters
                if held.session is waiter.session
                and held.socket is waiter.socket
                and held.operation() == waiter.operation()
            ]
        )

    def _cancel(self, waiters: list[Waiter]) -> None:
        for waiter in waiters:
            self._waiters.remove(waiter)
            self._give_up(waiter, CANCELLED)

    def _try(self, waiter: Waiter) -> bool:
        try:
            completion = waiter.attempt()
        except KernelError as error:
            self._give_up(waiter, error.code)
            return True
        if completion is None:
            return False
        deliver(waiter.request, completion)
        return True

    def _give_up(self, waiter: Waiter, code: int) -> None:
        if waiter.abandon is not None:
            waiter.abandon()
        services.refuse(waiter.request, code)
