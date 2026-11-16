from kernel_client import ipc
from kernel_client.services import Reply
from kernel_protocol.errors.codes import BAD_STATE, INVALID_ARGUMENT, OK, KernelError
from kernel_protocol.services.network import (
    ANY_PORT,
    KIND_STREAM,
    MAX_BACKLOG,
    MAX_TRANSFER_BYTES,
    STATE_BOUND,
    STATE_CLOSED,
    STATE_CONNECTED,
    STATE_CONNECTING,
    STATE_FINISHED,
    STATE_LISTENING,
    STATE_NEW,
    STATE_PEER_FINISHED,
    SocketDescription,
    encode_accepted,
    encode_word,
)
from kernel_services.network.limits import TCP_ORPHAN_PATIENCE_NANOSECONDS
from kernel_services.network.sockets.registry import Registry, Socket
from kernel_services.network.sockets.waiting import Completion, WaitList
from kernel_services.network.stack import Stack
from kernel_services.network.tcp import connection as tcp
from kernel_services.network.tcp.connection import Connection

OPENING_STATES = (tcp.SYN_SENT, tcp.SYN_RECEIVED)
NOT_CONNECTED = "the socket has no connection"
NOT_FRESH = "the socket already listens or has a connection"


class Orphan:
    def __init__(self, connection: Connection, now: int) -> None:
        self.connection = connection
        self._remaining_bytes = connection.unacknowledged_bytes()
        self._progressed_at = now

    def has_stalled(self, now: int) -> bool:
        remaining = self.connection.unacknowledged_bytes()
        if remaining < self._remaining_bytes:
            self._remaining_bytes = remaining
            self._progressed_at = now
        return remaining != 0 and now - self._progressed_at >= TCP_ORPHAN_PATIENCE_NANOSECONDS


class StreamSockets:
    def __init__(self, stack: Stack, registry: Registry, waits: WaitList) -> None:
        self._stack = stack
        self._registry = registry
        self._waits = waits
        self._orphans: list[Orphan] = []

    def bind(self, socket: Socket, port: int) -> int:
        if port == ANY_PORT or socket.bound_port != ANY_PORT or not self._is_fresh(socket):
            raise KernelError(INVALID_ARGUMENT, "a stream socket binds one port once")
        socket.bound_port = port
        return port

    def listen(self, socket: Socket, backlog: int) -> None:
        if not self._is_fresh(socket) or socket.bound_port == ANY_PORT:
            raise KernelError(BAD_STATE, "a socket binds a port before it listens")
        if backlog < 1 or backlog > MAX_BACKLOG:
            raise KernelError(INVALID_ARGUMENT, "backlog is outside the accepted range")
        socket.listener = self._stack.tcp.listen(socket.bound_port, backlog)

    def accept(self, request: ipc.Received, socket: Socket, timeout: int) -> None:
        listener = socket.listener
        if listener is None:
            raise KernelError(BAD_STATE, "the socket does not listen")

        def attempt() -> Completion | None:
            connection = listener.accept()
            if connection is None:
                return None
            try:
                accepted = self._registry.add_socket(socket.session, KIND_STREAM)
            except KernelError:
                self._stack.tcp.release(connection)
                raise
            accepted.connection = connection
            accepted.bound_port = connection.local_port
            reply = encode_accepted(
                accepted.handle, connection.remote_address, connection.remote_port
            )

            def undo() -> None:
                self.close(accepted)

            return Completion(Reply(reply), None, undo)

        self._waits.answer(request, socket.session, socket, timeout, self._stack.now, attempt)

    def connect(
        self, request: ipc.Received, socket: Socket, address: int, port: int, timeout: int
    ) -> None:
        if not self._is_fresh(socket):
            raise KernelError(BAD_STATE, NOT_FRESH)
        if not self._stack.interface.route.names_a_station(address) or port == ANY_PORT:
            raise KernelError(INVALID_ARGUMENT, "a connection names a station and a port")
        connection = self._stack.tcp.connect(address, port, self._stack.now)
        socket.connection = connection
        socket.bound_port = connection.local_port

        def attempt() -> Completion | None:
            if connection.state in OPENING_STATES:
                return None
            if connection.state == tcp.CLOSED and connection.error != OK:
                raise KernelError(connection.error, "the connection was not established")
            return Completion(Reply())

        def abandon() -> None:
            self._stack.tcp.release(connection)
            socket.connection = None
            socket.bound_port = ANY_PORT

        self._waits.answer(
            request, socket.session, socket, timeout, self._stack.now, attempt, abandon
        )

    def send(self, request: ipc.Received, socket: Socket, timeout: int, data: bytes) -> None:
        connection = self._connection_of(socket)
        if len(data) == 0 or len(data) > MAX_TRANSFER_BYTES:
            raise KernelError(INVALID_ARGUMENT, "a send carries between one byte and one transfer")

        def attempt() -> Completion | None:
            self._check(connection)
            if not connection.is_writable():
                raise KernelError(BAD_STATE, "the socket finished sending or was closed")
            accepted = connection.write(data, self._stack.now)
            if accepted == 0:
                return None
            return Completion(Reply(encode_word(accepted)))

        self._waits.answer(request, socket.session, socket, timeout, self._stack.now, attempt)

    def receive(self, request: ipc.Received, socket: Socket, timeout: int, limit: int) -> None:
        connection = self._connection_of(socket)
        if limit < 1:
            raise KernelError(INVALID_ARGUMENT, "a receive asks for at least one byte")
        if limit > MAX_TRANSFER_BYTES:
            limit = MAX_TRANSFER_BYTES

        def attempt() -> Completion | None:
            data = connection.peek(limit)
            if data:
                return Completion(Reply(data), lambda: connection.read(len(data)))
            self._check(connection)
            if connection.is_at_end_of_input():
                return Completion(Reply())
            return None

        self._waits.answer(request, socket.session, socket, timeout, self._stack.now, attempt)

    def finish(self, socket: Socket) -> None:
        connection = self._connection_of(socket)
        self._check(connection)
        connection.finish(self._stack.now)

    def close(self, socket: Socket) -> None:
        self._waits.cancel_socket(socket)
        self._registry.remove_socket(socket)
        if socket.listener is not None:
            self._stack.tcp.stop_listening(socket.listener)
            socket.listener = None
        connection = socket.connection
        socket.connection = None
        if connection is None:
            return
        has_unread_input = connection.readable_bytes() != 0
        if has_unread_input or connection.state in OPENING_STATES:
            self._stack.tcp.release(connection)
            return
        connection.finish(self._stack.now)
        if connection.state != tcp.CLOSED:
            self._orphans.append(Orphan(connection, self._stack.now))

    def reap(self) -> None:
        now = self._stack.now
        for orphan in list(self._orphans):
            connection = orphan.connection
            if connection.readable_bytes() != 0 or orphan.has_stalled(now):
                self._stack.tcp.release(connection)
            if connection.state == tcp.CLOSED:
                self._orphans.remove(orphan)

    def orphans(self) -> int:
        return len(self._orphans)

    def describe(self, socket: Socket) -> SocketDescription:
        connection = socket.connection
        if connection is None:
            state = STATE_NEW if socket.bound_port == ANY_PORT else STATE_BOUND
            if socket.listener is not None:
                state = STATE_LISTENING
            return SocketDescription(KIND_STREAM, state, socket.bound_port, 0, 0, 0, 0, OK)
        return SocketDescription(
            KIND_STREAM,
            self._state_of(connection),
            connection.local_port,
            connection.remote_address,
            connection.remote_port,
            connection.readable_bytes(),
            connection.writable_bytes() if connection.is_writable() else 0,
            connection.error,
        )

    def _state_of(self, connection: Connection) -> int:
        if connection.state in OPENING_STATES:
            return STATE_CONNECTING
        if connection.state == tcp.ESTABLISHED:
            return STATE_CONNECTED
        if connection.state == tcp.CLOSE_WAIT:
            return STATE_PEER_FINISHED
        if connection.state == tcp.CLOSED:
            return STATE_CLOSED
        return STATE_FINISHED

    def _is_fresh(self, socket: Socket) -> bool:
        return socket.connection is None and socket.listener is None

    def _connection_of(self, socket: Socket) -> Connection:
        if socket.connection is None:
            raise KernelError(BAD_STATE, NOT_CONNECTED)
        return socket.connection

    def _check(self, connection: Connection) -> None:
        if connection.error != OK:
            raise KernelError(connection.error, "the connection failed")
        if connection.state in OPENING_STATES:
            raise KernelError(BAD_STATE, "the connection is not established")
