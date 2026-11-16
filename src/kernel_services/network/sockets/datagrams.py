from kernel_client import ipc
from kernel_client.services import Reply
from kernel_protocol.errors.codes import (
    BAD_STATE,
    INVALID_ARGUMENT,
    MESSAGE_TOO_LARGE,
    OK,
    KernelError,
)
from kernel_protocol.services.network import (
    ANY_PORT,
    KIND_DATAGRAM,
    MAX_TRANSFER_BYTES,
    PEER_BYTES,
    SENDER_BYTES,
    STATE_BOUND,
    STATE_NEW,
    SocketDescription,
    encode_received_from,
)
from kernel_services.network.ipv4.address import is_host
from kernel_services.network.sockets.registry import Registry, Socket
from kernel_services.network.sockets.waiting import Completion, WaitList
from kernel_services.network.stack import Stack
from kernel_services.network.udp.ports import UdpPort

MAX_SEND_BYTES = MAX_TRANSFER_BYTES - PEER_BYTES
MAX_RECEIVE_BYTES = MAX_TRANSFER_BYTES - SENDER_BYTES


class DatagramSockets:
    def __init__(self, stack: Stack, registry: Registry, waits: WaitList) -> None:
        self._stack = stack
        self._registry = registry
        self._waits = waits

    def bind(self, socket: Socket, port: int) -> int:
        if socket.port is not None:
            raise KernelError(BAD_STATE, "the socket already has a port")
        socket.port = self._stack.udp.bind(port)
        socket.bound_port = socket.port.number
        return socket.bound_port

    def send_to(self, socket: Socket, address: int, port: int, data: bytes) -> int:
        if len(data) > MAX_SEND_BYTES:
            raise KernelError(MESSAGE_TOO_LARGE, "the datagram exceeds one transfer")
        route = self._stack.interface.route
        if port == ANY_PORT or not (is_host(address) or route.is_broadcast(address)):
            raise KernelError(INVALID_ARGUMENT, "a datagram names a station and a port")
        status = self._stack.udp.send(self._port_of(socket), address, port, data)
        if status != OK:
            raise KernelError(status, "the datagram was not sent")
        return len(data)

    def receive_from(self, request: ipc.Received, socket: Socket, timeout: int, limit: int) -> None:
        port = self._port_of(socket)
        if limit > MAX_RECEIVE_BYTES:
            limit = MAX_RECEIVE_BYTES

        def attempt() -> Completion | None:
            error = port.take_error()
            if error != OK:
                raise KernelError(error, "an earlier datagram was refused by its destination")
            first = port.first()
            if first is None:
                return None
            source, source_port, data = first
            reply = encode_received_from(source, source_port, len(data), data[:limit])
            return Completion(Reply(reply), port.take)

        self._waits.answer(request, socket.session, socket, timeout, self._stack.now, attempt)

    def close(self, socket: Socket) -> None:
        self._waits.cancel_socket(socket)
        self._registry.remove_socket(socket)
        if socket.port is not None:
            self._stack.udp.unbind(socket.port)
            socket.port = None

    def describe(self, socket: Socket) -> SocketDescription:
        port = socket.port
        if port is None:
            return SocketDescription(KIND_DATAGRAM, STATE_NEW, ANY_PORT, 0, 0, 0, 0, OK)
        return SocketDescription(
            KIND_DATAGRAM,
            STATE_BOUND,
            port.number,
            0,
            0,
            port.queued_bytes,
            MAX_SEND_BYTES,
            port.error,
        )

    def _port_of(self, socket: Socket) -> UdpPort:
        if socket.port is None:
            self.bind(socket, ANY_PORT)
        if socket.port is None:
            raise KernelError(BAD_STATE, "the socket has no port")
        return socket.port
