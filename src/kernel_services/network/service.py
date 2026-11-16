from kernel_client import capabilities, ipc, services
from kernel_client.processes import clock
from kernel_client.services import Reply
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    NOT_FOUND,
    OK,
    TIMED_OUT,
    UNSUPPORTED,
    KernelError,
)
from kernel_protocol.services.lifecycle import OPERATION_STOP
from kernel_protocol.services.network import (
    ACCESS_ALL,
    ACCESS_CONNECT,
    ACCESS_DATAGRAM,
    ACCESS_DELEGATE,
    ACCESS_ECHO,
    ACCESS_INSPECT,
    ACCESS_LISTEN,
    KIND_DATAGRAM,
    KIND_STREAM,
    MAX_ECHO_BYTES,
    OPERATION_ACCEPT,
    OPERATION_BIND,
    OPERATION_CLOSE,
    OPERATION_CONNECT,
    OPERATION_DESCRIBE,
    OPERATION_ECHO,
    OPERATION_ENTER,
    OPERATION_EVICT,
    OPERATION_FINISH,
    OPERATION_LEAVE,
    OPERATION_LISTEN,
    OPERATION_NEIGHBORS,
    OPERATION_OPEN,
    OPERATION_RECEIVE,
    OPERATION_RECEIVE_FROM,
    OPERATION_RESTRICT,
    OPERATION_REVOKE,
    OPERATION_ROOT,
    OPERATION_SEND,
    OPERATION_SEND_TO,
    OPERATION_STATUS,
    InterfaceStatus,
    decode_connect,
    decode_echo,
    decode_handle,
    decode_port,
    decode_receive,
    decode_request,
    decode_send,
    decode_send_to,
    decode_wait,
    decode_word,
    encode_description,
    encode_duration,
    encode_handle,
    encode_interface,
    encode_neighbors,
    encode_port,
    encode_session,
    encode_word,
)
from kernel_services.network.icmp import echo as echoes
from kernel_services.network.link import Link
from kernel_services.network.sockets.datagrams import DatagramSockets
from kernel_services.network.sockets.registry import Access, Registry, Session, Socket
from kernel_services.network.sockets.streams import StreamSockets
from kernel_services.network.sockets.waiting import Completion, WaitList
from kernel_services.network.stack import Stack

POLL = 0
REQUEST_BATCH = 16
MAX_PENDING_ENTRIES = 16
IDLE_SLICE_NANOSECONDS = 10000000
BUSY_SLICE_NANOSECONDS = 1000000
CLOSING_GRACE_NANOSECONDS = 200000000
ECHO_SEQUENCES = 0x10000
ECHO_PATTERN = bytes(range(256)) * 4
SUPERVISOR_ONLY = "only the supervisor of the service asks for this"


class NetworkService:
    def __init__(
        self, stack: Stack, link: Link, endpoint: int, instance: int, supervisor: int
    ) -> None:
        self._stack = stack
        self._link = link
        self._endpoint = endpoint
        self._supervisor = supervisor
        self._registry = Registry(instance)
        self._waits = WaitList()
        self._streams = StreamSockets(stack, self._registry, self._waits)
        self._datagrams = DatagramSockets(stack, self._registry, self._waits)
        self._entering: dict[int, Access] = {}
        self._top = self._registry.add_access(ipc.create_endpoint(), ACCESS_ALL)
        self._is_linked = True
        self._echo_sequence = 0
        self._by_session = {
            OPERATION_LEAVE: self._leave,
            OPERATION_RESTRICT: self._restrict,
            OPERATION_REVOKE: self._revoke,
            OPERATION_STATUS: self._status,
            OPERATION_NEIGHBORS: self._neighbors,
            OPERATION_ECHO: self._echo,
            OPERATION_OPEN: self._open,
        }
        self._by_socket = {
            OPERATION_BIND: self._bind,
            OPERATION_LISTEN: self._listen,
            OPERATION_ACCEPT: self._accept,
            OPERATION_CONNECT: self._connect,
            OPERATION_SEND: self._send,
            OPERATION_RECEIVE: self._receive,
            OPERATION_SEND_TO: self._send_to,
            OPERATION_RECEIVE_FROM: self._receive_from,
            OPERATION_FINISH: self._finish,
            OPERATION_CLOSE: self._close,
            OPERATION_DESCRIBE: self._describe,
        }

    def run(self) -> bool:
        while not self.step():
            continue
        return True

    def step(self) -> bool:
        self._turn(self._wake_time(clock()))
        if self._serve_requests():
            return True
        self._settle()
        return False

    def _turn(self, wake_time: int) -> None:
        for frame in self._link.receive(wake_time):
            self._stack.frame_arrives(frame, clock())
        self._stack.advance(clock())

    def _settle(self) -> None:
        self._stack.run(clock())
        self._waits.settle(self._stack.now)
        self._streams.reap()
        self._watch_link()
        self._link.transmit(self._stack.take_frames())

    def _wake_time(self, now: int) -> int:
        is_busy = self._waits.count() != 0 or self._stack.tcp.connection_count() != 0
        wake_time = now + (BUSY_SLICE_NANOSECONDS if is_busy else IDLE_SLICE_NANOSECONDS)
        wake_time = self._stack.next_deadline(wake_time)
        return self._waits.next_deadline(wake_time)

    def _watch_link(self) -> None:
        if self._link.has_failed() and self._link.recover(self._stack.now):
            print(f"network: device=recovered resets={self._link.resets()}")
        is_linked = self._link.is_linked()
        if is_linked != self._is_linked:
            self._is_linked = is_linked
            self._stack.interface.link_changed(is_linked)
            state = "up" if is_linked else "down"
            print(f"network: link={state}")

    def _serve_requests(self) -> bool:
        for _ in range(REQUEST_BATCH):
            try:
                request = ipc.receive(self._endpoint, POLL)
            except KernelError as error:
                if error.code != TIMED_OUT:
                    raise
                return False
            if self._request_arrives(request):
                return True
        return False

    def _request_arrives(self, request: ipc.Received) -> bool:
        if request.reply == 0:
            services.discard_transfer(request)
            return False
        if request.transferred != ipc.NO_TRANSFER:
            services.discard_transfer(request)
            services.refuse(request, INVALID_ARGUMENT)
            return False
        if request.message.operation == OPERATION_STOP:
            return self._stop(request)
        try:
            reply = self._handle(request)
        except KernelError as error:
            services.refuse(request, error.code)
            return False
        if reply is not None:
            services.respond(request, reply)
        return False

    def _handle(self, request: ipc.Received) -> Reply | None:
        operation = request.message.operation
        if operation == OPERATION_ENTER:
            return self._enter(request.sender)
        if operation in (OPERATION_ROOT, OPERATION_EVICT):
            return self._supervise(request)
        instance, subject, body = decode_request(request.message.payload)
        by_session = self._by_session.get(operation)
        if by_session is not None:
            session = self._registry.session_of(instance, subject, request.sender)
            return by_session(request, session, body)
        by_socket = self._by_socket.get(operation)
        if by_socket is None:
            raise KernelError(UNSUPPORTED, "operation is not part of the network service")
        return by_socket(request, self._registry.socket_of(instance, subject, request.sender), body)

    def _stop(self, request: ipc.Received) -> bool:
        if request.sender != self._supervisor:
            services.refuse(request, ACCESS_DENIED)
            return False
        self._waits.cancel_all()
        for session in list(self._registry.sessions.values()):
            self._end_session(session)
        self._drain(clock() + CLOSING_GRACE_NANOSECONDS)
        self._stack.tcp.abort_all()
        self._stack.udp.unbind_all()
        self._link.transmit(self._stack.take_frames())
        self._drop_access(self._top)
        self._link.close()
        services.respond(request, Reply())
        return True

    def _drain(self, deadline: int) -> None:
        while self._streams.orphans() != 0 and clock() < deadline:
            self._turn(clock() + BUSY_SLICE_NANOSECONDS)
            self._settle()

    def _supervise(self, request: ipc.Received) -> Reply:
        if request.sender != self._supervisor:
            raise KernelError(ACCESS_DENIED, SUPERVISOR_ONLY)
        if request.message.operation == OPERATION_ROOT:
            return Reply(b"", self._top.endpoint)
        client = decode_handle(request.message.payload)
        self._entering.pop(client, None)
        for session in self._registry.sessions_of_client(client):
            self._end_session(session)
        return Reply()

    def _enter(self, sender: int) -> Reply:
        for access in list(self._registry.accesses.values()):
            self._collect(access)
        entered = self._entering.get(sender)
        if entered is None or entered.identity not in self._registry.accesses:
            raise KernelError(ACCESS_DENIED, "no network access capability was presented")
        del self._entering[sender]
        session = self._registry.add_session(sender, entered)
        return Reply(encode_session(self._registry.instance, session.token, entered.rights))

    def _collect(self, access: Access) -> None:
        while True:
            try:
                note = ipc.receive(access.endpoint, POLL)
            except KernelError as error:
                if error.code != TIMED_OUT:
                    raise
                return
            services.discard_transfer(note)
            if note.reply != 0:
                services.refuse(note, UNSUPPORTED)
            elif note.message.operation == OPERATION_ENTER and (
                note.sender in self._entering or len(self._entering) < MAX_PENDING_ENTRIES
            ):
                self._entering[note.sender] = access

    def _leave(self, request: ipc.Received, session: Session, body: bytes) -> Reply:
        self._end_session(session)
        return Reply()

    def _restrict(self, request: ipc.Received, session: Session, body: bytes) -> Reply:
        rights = decode_word(body)
        granted = session.access.rights
        if granted & ACCESS_DELEGATE == 0:
            raise KernelError(ACCESS_DENIED, "the access does not grant delegation")
        if rights == 0 or rights & ~ACCESS_ALL:
            raise KernelError(INVALID_ARGUMENT, "restriction asks for no right or unknown rights")
        if rights & ~granted:
            raise KernelError(
                ACCESS_DENIED, "a restricted access holds no more rights than its origin"
            )
        endpoint = ipc.create_endpoint()
        try:
            access = self._registry.add_access(endpoint, rights)
        except KernelError:
            capabilities.close(endpoint)
            raise
        access.parent = session.access
        access.owner = session
        return Reply(encode_word(access.identity), endpoint)

    def _revoke(self, request: ipc.Received, session: Session, body: bytes) -> Reply:
        access = self._registry.accesses.get(decode_word(body))
        if access is None or access.owner is not session:
            raise KernelError(NOT_FOUND, "the session created no such access")
        self._drop_access(access)
        return Reply()

    def _status(self, request: ipc.Received, session: Session, body: bytes) -> Reply:
        self._require(session, ACCESS_INSPECT)
        interface = self._stack.interface
        status = InterfaceStatus(
            hardware=interface.hardware,
            address=interface.route.address,
            prefix=interface.route.prefix,
            gateway=interface.route.gateway,
            mtu=interface.mtu,
            is_linked=self._is_linked,
            sockets=len(self._registry.sockets),
            connections=self._stack.tcp.connection_count(),
            buffered_bytes=self._stack.budget.used_bytes,
            resets=self._link.resets(),
            counters=self._stack.counters.values(),
        )
        return Reply(encode_interface(status))

    def _neighbors(self, request: ipc.Received, session: Session, body: bytes) -> Reply:
        self._require(session, ACCESS_INSPECT)
        return Reply(encode_neighbors(self._stack.interface.neighbors.entries()))

    def _echo(self, request: ipc.Received, session: Session, body: bytes) -> None:
        self._require(session, ACCESS_ECHO)
        address, timeout, data_bytes = decode_echo(body)
        if not self._stack.interface.route.names_a_station(address) or data_bytes > MAX_ECHO_BYTES:
            raise KernelError(INVALID_ARGUMENT, "an echo names a station and a bounded size")
        self._echo_sequence = (self._echo_sequence + 1) % ECHO_SEQUENCES
        identity = ((session.token % ECHO_SEQUENCES) << 16) | self._echo_sequence
        echo = self._stack.echoes.start(
            address, identity, ECHO_PATTERN[:data_bytes], self._stack.now
        )
        status = self._stack.send_echo(address, identity, echo.data)
        if status != OK:
            self._stack.echoes.cancel(echo)
            raise KernelError(status, "the echo request was not sent")

        def attempt() -> Completion | None:
            if echo.status == echoes.PENDING:
                return None
            if echo.status != OK:
                raise KernelError(echo.status, "the echo request did not reach its destination")
            return Completion(Reply(encode_duration(echo.round_trip_nanoseconds)))

        def abandon() -> None:
            self._stack.echoes.cancel(echo)

        self._waits.answer(request, session, None, timeout, self._stack.now, attempt, abandon)

    def _open(self, request: ipc.Received, session: Session, body: bytes) -> Reply:
        kind = decode_word(body)
        if kind == KIND_STREAM:
            if session.access.rights & (ACCESS_CONNECT | ACCESS_LISTEN) == 0:
                raise KernelError(ACCESS_DENIED, "the access grants no stream socket")
        elif kind == KIND_DATAGRAM:
            self._require(session, ACCESS_DATAGRAM)
        else:
            raise KernelError(INVALID_ARGUMENT, "unknown socket kind")
        return Reply(encode_handle(self._registry.add_socket(session, kind).handle))

    def _bind(self, request: ipc.Received, socket: Socket, body: bytes) -> Reply:
        port = decode_port(body)
        if socket.kind == KIND_STREAM:
            return Reply(encode_port(self._streams.bind(socket, port)))
        return Reply(encode_port(self._datagrams.bind(socket, port)))

    def _listen(self, request: ipc.Received, socket: Socket, body: bytes) -> Reply:
        self._require(socket.session, ACCESS_LISTEN)
        self._streams.listen(self._stream(socket), decode_port(body))
        return Reply()

    def _accept(self, request: ipc.Received, socket: Socket, body: bytes) -> None:
        self._streams.accept(request, self._stream(socket), decode_wait(body))

    def _connect(self, request: ipc.Received, socket: Socket, body: bytes) -> None:
        self._require(socket.session, ACCESS_CONNECT)
        address, port, timeout = decode_connect(body)
        self._streams.connect(request, self._stream(socket), address, port, timeout)

    def _send(self, request: ipc.Received, socket: Socket, body: bytes) -> None:
        timeout, data = decode_send(body)
        self._streams.send(request, self._stream(socket), timeout, data)

    def _receive(self, request: ipc.Received, socket: Socket, body: bytes) -> None:
        timeout, limit = decode_receive(body)
        self._streams.receive(request, self._stream(socket), timeout, limit)

    def _send_to(self, request: ipc.Received, socket: Socket, body: bytes) -> Reply:
        address, port, data = decode_send_to(body)
        sent = self._datagrams.send_to(self._datagram(socket), address, port, data)
        return Reply(encode_word(sent))

    def _receive_from(self, request: ipc.Received, socket: Socket, body: bytes) -> None:
        timeout, limit = decode_receive(body)
        self._datagrams.receive_from(request, self._datagram(socket), timeout, limit)

    def _finish(self, request: ipc.Received, socket: Socket, body: bytes) -> Reply:
        self._streams.finish(self._stream(socket))
        return Reply()

    def _close(self, request: ipc.Received, socket: Socket, body: bytes) -> Reply:
        self._release(socket)
        return Reply()

    def _describe(self, request: ipc.Received, socket: Socket, body: bytes) -> Reply:
        if socket.kind == KIND_STREAM:
            return Reply(encode_description(self._streams.describe(socket)))
        return Reply(encode_description(self._datagrams.describe(socket)))

    def _release(self, socket: Socket) -> None:
        if socket.kind == KIND_STREAM:
            self._streams.close(socket)
        else:
            self._datagrams.close(socket)

    def _end_session(self, session: Session) -> None:
        self._waits.cancel_session(session)
        for socket in self._registry.sockets_of(session):
            self._release(socket)
        for access in self._registry.created_by(session):
            self._drop_access(access)
        self._registry.remove_session(session)

    def _drop_access(self, access: Access) -> None:
        if access.identity not in self._registry.accesses:
            return
        for derived in self._registry.derived_from(access):
            self._drop_access(derived)
        for session in self._registry.sessions_through(access):
            self._end_session(session)
        self._registry.remove_access(access)

    def _require(self, session: Session, right: int) -> None:
        if session.access.rights & right == 0:
            raise KernelError(ACCESS_DENIED, "the access does not grant this operation")

    def _stream(self, socket: Socket) -> Socket:
        if socket.kind != KIND_STREAM:
            raise KernelError(NOT_FOUND, "the operation needs a stream socket")
        return socket

    def _datagram(self, socket: Socket) -> Socket:
        if socket.kind != KIND_DATAGRAM:
            raise KernelError(NOT_FOUND, "the operation needs a datagram socket")
        return socket
