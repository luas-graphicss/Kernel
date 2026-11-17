from kernel_client import ipc, services
from kernel_client.processes import clock
from kernel_client.services import Reply
from kernel_drivers.uart.port import SerialPort
from kernel_protocol.devices.layout import SERIAL_TRANSFER_BYTES
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    CANCELLED,
    INVALID_ARGUMENT,
    MESSAGE_TOO_LARGE,
    TIMED_OUT,
    UNSUPPORTED,
    KernelError,
)
from kernel_protocol.services.console import (
    MAX_LINE_BYTES,
    MAX_PENDING_LINES,
    MAX_WRITE_BYTES,
    OPERATION_READ_LINE,
    OPERATION_WRITE,
    decode_timeout,
    encode_count,
)
from kernel_protocol.services.lifecycle import OPERATION_STOP
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER
from kernel_services.console.discipline import (
    LINE_FEED_BYTES,
    NEW_LINE,
    LineDiscipline,
    OverlongLine,
)

POLL = 0
INPUT_SLICE_NANOSECONDS = 5000000
WRITE_TIMEOUT_NANOSECONDS = 1000000000
ECHO_TIMEOUT_NANOSECONDS = 50000000


def write_text(port: SerialPort, data: bytes, deadline: int) -> int:
    accepted = 0
    while accepted < len(data):
        line_feed = data.find(LINE_FEED_BYTES, accepted)
        end = len(data) if line_feed < 0 else line_feed
        accepted += port.write(data[accepted:end], deadline)
        if accepted < end:
            break
        if line_feed >= 0:
            if port.write(NEW_LINE, deadline) != len(NEW_LINE):
                break
            accepted += 1
    return accepted


class Console:
    def __init__(self, port: SerialPort, endpoint: int, supervisor: int) -> None:
        self._port = port
        self._endpoint = endpoint
        self._supervisor = supervisor
        self._discipline = LineDiscipline(MAX_LINE_BYTES, MAX_PENDING_LINES)
        self._reader: ipc.Received | None = None
        self._reader_deadline = DEADLINE_NEVER

    def run(self) -> bool:
        while True:
            request = self._next()
            if request is None:
                self._pump()
            elif request.reply == 0:
                services.discard_transfer(request)
            elif self._dispatch(request):
                return True

    def _next(self) -> ipc.Received | None:
        if self._reader is None:
            return ipc.receive(self._endpoint)
        try:
            return ipc.receive(self._endpoint, POLL)
        except KernelError as error:
            if error.code != TIMED_OUT:
                raise
        return None

    def _dispatch(self, request: ipc.Received) -> bool:
        operation = request.message.operation
        if request.transferred != ipc.NO_TRANSFER:
            services.discard_transfer(request)
            services.refuse(request, INVALID_ARGUMENT)
        elif operation == OPERATION_STOP:
            return self._stop(request)
        elif operation == OPERATION_WRITE:
            self._write(request)
        elif operation == OPERATION_READ_LINE:
            self._read_line(request)
        else:
            services.refuse(request, UNSUPPORTED)
        return False

    def _stop(self, request: ipc.Received) -> bool:
        if request.sender != self._supervisor:
            services.refuse(request, ACCESS_DENIED)
            return False
        if self._reader is not None:
            services.refuse(self._reader, CANCELLED)
            self._reader = None
        services.respond(request, Reply())
        return True

    def _write(self, request: ipc.Received) -> None:
        data = request.message.payload
        if len(data) > MAX_WRITE_BYTES:
            services.refuse(request, MESSAGE_TOO_LARGE)
            return
        accepted = write_text(self._port, data, clock() + WRITE_TIMEOUT_NANOSECONDS)
        services.respond(request, Reply(encode_count(accepted)))

    def _read_line(self, request: ipc.Received) -> None:
        try:
            timeout = decode_timeout(request.message.payload)
        except KernelError as error:
            services.refuse(request, error.code)
            return
        if self._reader is not None:
            services.refuse(self._reader, CANCELLED)
        self._reader = request
        self._reader_deadline = DEADLINE_NEVER
        if timeout != DEADLINE_NEVER:
            self._reader_deadline = clock() + timeout
        self._settle()

    def _pump(self) -> None:
        slice_end = clock() + INPUT_SLICE_NANOSECONDS
        if slice_end > self._reader_deadline:
            slice_end = self._reader_deadline
        received = self._port.read(SERIAL_TRANSFER_BYTES, slice_end)
        if received:
            echo = self._discipline.feed(received)
            self._port.write(echo, clock() + ECHO_TIMEOUT_NANOSECONDS)
        self._settle()

    def _settle(self) -> None:
        reader = self._reader
        if reader is None:
            return
        line = self._discipline.take_line()
        if line is None:
            if clock() >= self._reader_deadline:
                self._reader = None
                services.refuse(reader, TIMED_OUT)
            return
        self._reader = None
        if isinstance(line, OverlongLine):
            services.refuse(reader, MESSAGE_TOO_LARGE)
        else:
            services.respond(reader, Reply(line))
