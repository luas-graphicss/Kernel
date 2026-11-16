from kernel_client import services
from kernel_protocol.errors.codes import ACCESS_DENIED, PEER_CLOSED, KernelError
from kernel_protocol.services.network import (
    ANY_PORT,
    KIND_DATAGRAM,
    KIND_STREAM,
    MAX_TRANSFER_BYTES,
    OPERATION_ACCEPT,
    OPERATION_BIND,
    OPERATION_CLOSE,
    OPERATION_CONNECT,
    OPERATION_DESCRIBE,
    OPERATION_ECHO,
    OPERATION_ENTER,
    OPERATION_FINISH,
    OPERATION_LEAVE,
    OPERATION_LISTEN,
    OPERATION_NEIGHBORS,
    OPERATION_OPEN,
    OPERATION_RECEIVE,
    OPERATION_RECEIVE_FROM,
    OPERATION_RESTRICT,
    OPERATION_REVOKE,
    OPERATION_SEND,
    OPERATION_SEND_TO,
    OPERATION_STATUS,
    PEER_BYTES,
    SENDER_BYTES,
    WAIT_FOREVER,
    InterfaceStatus,
    SocketDescription,
    decode_accepted,
    decode_description,
    decode_duration,
    decode_handle,
    decode_interface,
    decode_neighbors,
    decode_port,
    decode_received_from,
    decode_session,
    decode_word,
    encode_connect,
    encode_echo,
    encode_port,
    encode_receive,
    encode_request,
    encode_send,
    encode_send_to,
    encode_wait,
    encode_word,
)

DEFAULT_ECHO_BYTES = 32
MAX_DATAGRAM_BYTES = MAX_TRANSFER_BYTES - PEER_BYTES
MAX_RECEIVED_DATAGRAM_BYTES = MAX_TRANSFER_BYTES - SENDER_BYTES
SEND_CHUNK_BYTES = MAX_TRANSFER_BYTES - 8
REVOKED = "the network access was revoked"


class Network:
    def __init__(self, service: int, access: int) -> None:
        self._service = service
        try:
            services.note(access, OPERATION_ENTER)
        except KernelError as error:
            if error.code != PEER_CLOSED:
                raise
            raise KernelError(ACCESS_DENIED, REVOKED) from None
        payload, _received = services.call(service, OPERATION_ENTER)
        self.instance, self.session, self.rights = decode_session(payload)

    def request(self, operation: int, subject: int, body: bytes = b"") -> bytes:
        payload, _received = services.call(
            self._service, operation, encode_request(self.instance, subject, body)
        )
        return payload

    def status(self) -> InterfaceStatus:
        return decode_interface(self.request(OPERATION_STATUS, self.session))

    def neighbors(self) -> list[tuple[int, bytes]]:
        return decode_neighbors(self.request(OPERATION_NEIGHBORS, self.session))

    def echo(
        self, address: int, timeout_nanoseconds: int, data_bytes: int = DEFAULT_ECHO_BYTES
    ) -> int:
        body = encode_echo(address, timeout_nanoseconds, data_bytes)
        return decode_duration(self.request(OPERATION_ECHO, self.session, body))

    def restrict(self, rights: int) -> tuple[int, int]:
        payload, capability = services.call(
            self._service,
            OPERATION_RESTRICT,
            encode_request(self.instance, self.session, encode_word(rights)),
        )
        return decode_word(payload), capability

    def revoke(self, access: int) -> None:
        self.request(OPERATION_REVOKE, self.session, encode_word(access))

    def stream(self) -> "StreamSocket":
        return StreamSocket(self, self._open(KIND_STREAM))

    def datagram(self) -> "DatagramSocket":
        return DatagramSocket(self, self._open(KIND_DATAGRAM))

    def leave(self) -> None:
        self.request(OPERATION_LEAVE, self.session)

    def _open(self, kind: int) -> int:
        return decode_handle(self.request(OPERATION_OPEN, self.session, encode_word(kind)))


class Socket:
    def __init__(self, network: Network, handle: int) -> None:
        self._network = network
        self.handle = handle

    def bind(self, port: int = ANY_PORT) -> int:
        return decode_port(self._call(OPERATION_BIND, encode_port(port)))

    def describe(self) -> SocketDescription:
        return decode_description(self._call(OPERATION_DESCRIBE))

    def close(self) -> None:
        self._call(OPERATION_CLOSE)

    def _call(self, operation: int, body: bytes = b"") -> bytes:
        return self._network.request(operation, self.handle, body)


class StreamSocket(Socket):
    def listen(self, backlog: int) -> None:
        self._call(OPERATION_LISTEN, encode_port(backlog))

    def accept(self, timeout_nanoseconds: int = WAIT_FOREVER) -> tuple["StreamSocket", int, int]:
        handle, address, port = decode_accepted(
            self._call(OPERATION_ACCEPT, encode_wait(timeout_nanoseconds))
        )
        return StreamSocket(self._network, handle), address, port

    def connect(self, address: int, port: int, timeout_nanoseconds: int = WAIT_FOREVER) -> None:
        self._call(OPERATION_CONNECT, encode_connect(address, port, timeout_nanoseconds))

    def send(self, data: bytes, timeout_nanoseconds: int = WAIT_FOREVER) -> int:
        chunk = data if len(data) <= SEND_CHUNK_BYTES else data[:SEND_CHUNK_BYTES]
        return decode_word(self._call(OPERATION_SEND, encode_send(timeout_nanoseconds, chunk)))

    def send_all(self, data: bytes, timeout_nanoseconds: int = WAIT_FOREVER) -> None:
        sent = 0
        while sent < len(data):
            sent += self.send(data[sent : sent + SEND_CHUNK_BYTES], timeout_nanoseconds)

    def receive(self, limit: int, timeout_nanoseconds: int = WAIT_FOREVER) -> bytes:
        return self._call(OPERATION_RECEIVE, encode_receive(timeout_nanoseconds, limit))

    def finish(self) -> None:
        self._call(OPERATION_FINISH)


class DatagramSocket(Socket):
    def send_to(self, address: int, port: int, data: bytes) -> int:
        return decode_word(self._call(OPERATION_SEND_TO, encode_send_to(address, port, data)))

    def receive_from(
        self, limit: int, timeout_nanoseconds: int = WAIT_FOREVER
    ) -> tuple[int, int, int, bytes]:
        return decode_received_from(
            self._call(OPERATION_RECEIVE_FROM, encode_receive(timeout_nanoseconds, limit))
        )
