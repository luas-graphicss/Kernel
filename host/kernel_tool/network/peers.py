import hashlib
import socket
import threading
import time
from collections.abc import Callable
from functools import partial

from kernel_tool.network.plan import (
    ECHO_PORT,
    GREETING_PORT,
    REQUEST_BYTES,
    SILENT_PORT,
    SINK_PORT,
    SLOW_PORT,
    SOURCE_PORT,
    decode_source_request,
    greeting,
    stream,
)

type Report = Callable[[dict[str, object]], None]

ACCEPT_POLL_SECONDS = 0.2
CONNECTION_TIMEOUT_SECONDS = 120.0
CHUNK_BYTES = 4096
SLOW_CHUNK_BYTES = 1024
SLOW_PAUSE_SECONDS = 0.02
DATAGRAM_BYTES = 65535
BACKLOG = 16


class Peers:
    def __init__(self, address: str, guest: str, report: Report) -> None:
        self._address = address
        self._guest = guest
        self._report = report
        self._stopping = threading.Event()
        self._threads: list[threading.Thread] = []
        self._held: list[socket.socket] = []

    def start(self) -> None:
        self._serve(ECHO_PORT, self._echo)
        self._serve(SINK_PORT, self._sink)
        self._serve(SLOW_PORT, self._slow_sink)
        self._serve(SOURCE_PORT, self._source)
        self._serve(SILENT_PORT, self._hold)
        self._serve(GREETING_PORT, self._greet)
        self._run(self._echo_datagrams)

    def stop(self) -> None:
        self._stopping.set()
        for held in self._held:
            held.close()
        for thread in self._threads:
            thread.join(timeout=ACCEPT_POLL_SECONDS * 4)

    def call(self, port: int, seed: int, length: int) -> None:
        self._run(lambda: self._call(port, seed, length))

    def _run(self, target: Callable[[], None]) -> None:
        thread = threading.Thread(target=target, daemon=True)
        self._threads.append(thread)
        thread.start()

    def _serve(self, port: int, handler: Callable[[socket.socket, str], None]) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self._address, port))
        listener.listen(BACKLOG)
        listener.settimeout(ACCEPT_POLL_SECONDS)
        self._run(lambda: self._accept(listener, port, handler))

    def _accept(
        self, listener: socket.socket, port: int, handler: Callable[[socket.socket, str], None]
    ) -> None:
        with listener:
            while not self._stopping.is_set():
                try:
                    connection, peer = listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                connection.settimeout(CONNECTION_TIMEOUT_SECONDS)
                name = f"{peer[0]}:{peer[1]}"
                self._run(partial(self._handle, port, handler, connection, name))

    def _handle(
        self,
        port: int,
        handler: Callable[[socket.socket, str], None],
        connection: socket.socket,
        peer: str,
    ) -> None:
        try:
            handler(connection, peer)
        except OSError as error:
            self._report({"event": "peer-error", "port": port, "peer": peer, "error": str(error)})
        finally:
            if connection not in self._held:
                connection.close()

    def _echo(self, connection: socket.socket, peer: str) -> None:
        echoed = 0
        while chunk := connection.recv(CHUNK_BYTES):
            connection.sendall(chunk)
            echoed += len(chunk)
        self._report({"event": "echo", "peer": peer, "bytes": echoed})

    def _sink(self, connection: socket.socket, peer: str) -> None:
        self._digest(connection, peer, "sink", CHUNK_BYTES, 0.0)

    def _slow_sink(self, connection: socket.socket, peer: str) -> None:
        self._digest(connection, peer, "slow-sink", SLOW_CHUNK_BYTES, SLOW_PAUSE_SECONDS)

    def _digest(
        self, connection: socket.socket, peer: str, name: str, chunk_bytes: int, pause: float
    ) -> None:
        digest = hashlib.sha256()
        received = 0
        while chunk := connection.recv(chunk_bytes):
            digest.update(chunk)
            received += len(chunk)
            if pause:
                time.sleep(pause)
        connection.sendall(digest.digest())
        self._report({"event": name, "peer": peer, "bytes": received, "sha256": digest.hexdigest()})

    def _source(self, connection: socket.socket, peer: str) -> None:
        request = b""
        while len(request) < REQUEST_BYTES:
            chunk = connection.recv(REQUEST_BYTES - len(request))
            if not chunk:
                return
            request += chunk
        seed, length = decode_source_request(request)
        connection.sendall(stream(seed, length))
        self._report({"event": "source", "peer": peer, "seed": seed, "bytes": length})

    def _greet(self, connection: socket.socket, peer: str) -> None:
        text = greeting()
        connection.sendall(text)
        self._report(
            {
                "event": "greeting",
                "peer": peer,
                "bytes": len(text),
                "sha256": hashlib.sha256(text).hexdigest(),
            }
        )

    def _hold(self, connection: socket.socket, peer: str) -> None:
        self._held.append(connection)
        self._report({"event": "held", "peer": peer})

    def _echo_datagrams(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as datagrams:
            datagrams.bind((self._address, ECHO_PORT))
            datagrams.settimeout(ACCEPT_POLL_SECONDS)
            while not self._stopping.is_set():
                try:
                    data, sender = datagrams.recvfrom(DATAGRAM_BYTES)
                except TimeoutError:
                    continue
                datagrams.sendto(data, sender)

    def _call(self, port: int, seed: int, length: int) -> None:
        sent = stream(seed, length)
        returned = bytearray()
        outcome: dict[str, object] = {"event": "call", "port": port, "bytes": length}
        try:
            with socket.create_connection(
                (self._guest, port), timeout=CONNECTION_TIMEOUT_SECONDS
            ) as connection:
                connection.sendall(sent)
                connection.shutdown(socket.SHUT_WR)
                while chunk := connection.recv(CHUNK_BYTES):
                    returned.extend(chunk)
        except OSError as error:
            outcome["error"] = str(error)
        outcome["returned"] = len(returned)
        outcome["sha256"] = hashlib.sha256(returned).hexdigest()
        outcome["matches"] = bytes(returned) == sent
        self._report(outcome)
