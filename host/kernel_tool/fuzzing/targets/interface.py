import inspect
from collections.abc import Callable

from kernel_apps.shell.words import split_words
from kernel_protocol.errors.codes import OK, KernelError
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services import (
    block,
    console,
    control,
    entropy,
    files,
    launch,
    lifecycle,
    network,
    network_settings,
)
from kernel_protocol.services.console import MAX_LINE_BYTES, MAX_PENDING_LINES
from kernel_protocol.wire.message import (
    FLAG_ERROR,
    FLAG_REPLY,
    Message,
    decode_message,
    encode_message,
)
from kernel_protocol.wire.spawn import REQUEST_BYTES, encode_spawn_request
from kernel_services.console.discipline import LineDiscipline, OverlongLine
from kernel_tool.fuzzing.model import Family, InterpretedTarget, InvariantError, NativeTarget
from kernel_tool.fuzzing.native import IPC_MESSAGE_ENTRY, SPAWN_REQUEST_ENTRY
from kernel_tool.fuzzing.targets.text import guest_text
from kernel_tool.outcome import CheckError

SERVICE_MODULES = (
    block,
    console,
    control,
    entropy,
    files,
    launch,
    lifecycle,
    network,
    network_settings,
)
DECODER_PREFIX = "decode_"
MAX_MESSAGE_BYTES = 4160
MAX_PAYLOAD_BYTES = 4128
MAX_CONSOLE_BYTES = 2048
SEED_PAYLOAD_BYTES = (0, 8, 16, 64)
SEED_PROGRAM = "kernel_services.echo.main"
SEED_PRIORITY = 2
SEED_HANDLE = 5

type Decoder = Callable[[bytes], object]


def service_decoders() -> tuple[Decoder, ...]:
    decoders = []
    for module in SERVICE_MODULES:
        for name in sorted(vars(module)):
            if not name.startswith(DECODER_PREFIX):
                continue
            decoder = getattr(module, name)
            if len(inspect.signature(decoder).parameters) != 1:
                raise CheckError(f"{module.__name__}.{name} does not decode a single payload")
            decoders.append(decoder)
    return tuple(decoders)


DECODERS = service_decoders()


def message_seeds() -> tuple[bytes, ...]:
    return (
        encode_message(Message(1, 0, 1, b"")),
        encode_message(Message(0x1122_3344, FLAG_REPLY, 0x0102_0304_0506_0708, bytes(16))),
        encode_message(Message(7, FLAG_REPLY | FLAG_ERROR, 9, bytes(4))),
    )


def compare_message_parsers(data: bytes, native_status: int) -> None:
    try:
        decode_message(data)
    except KernelError as error:
        expected = -error.code
    else:
        expected = OK
    if native_status != expected:
        raise InvariantError("the supervisor and the Python codec disagree about a message")


def spawn_request_seeds() -> tuple[bytes, ...]:
    return (
        encode_spawn_request(SEED_PROGRAM, b"argument", SEED_PRIORITY, 0, 0, ()),
        encode_spawn_request(
            SEED_PROGRAM, b"", SEED_PRIORITY, 0x10_0000, 0x1_0000, ((SEED_HANDLE, RIGHT_SEND),)
        ),
        bytes(REQUEST_BYTES),
    )


def service_payload_seeds() -> tuple[bytes, ...]:
    return tuple(
        bytes((index,)) + bytes(size)
        for index in range(len(DECODERS))
        for size in SEED_PAYLOAD_BYTES
    )


def decode_service_payload(data: bytes) -> None:
    if data:
        DECODERS[data[0] % len(DECODERS)](data[1:])


def console_seeds() -> tuple[bytes, ...]:
    return (
        b"help\n",
        b'write data/note "two words"\r\nls data\r',
        b"first line\rsecomd\x7f\x7fnd line\n",
        b"cat \xc3\xa9\x7f\x15ps\n",
        b"ls\tboot\x1b[A\x1bOP\r",
    )


def type_on_the_console(data: bytes) -> None:
    discipline = LineDiscipline(MAX_LINE_BYTES, MAX_PENDING_LINES)
    discipline.feed(data)
    while True:
        line = discipline.take_line()
        if line is None:
            return
        if isinstance(line, OverlongLine):
            continue
        if len(line) > MAX_LINE_BYTES:
            raise InvariantError("the console delivered a line longer than its limit")
        try:
            split_words(guest_text(line))
        except KernelError:
            continue


TARGETS = (
    NativeTarget(
        name="ipc-message",
        family=Family.INTERFACE,
        sources=(
            "native/supervisor/ipc/message.c",
            "native/include/kernel/abi/ipc.h",
            "src/kernel_protocol/wire/message.py",
        ),
        max_input_bytes=MAX_MESSAGE_BYTES,
        seeds=message_seeds,
        entry=IPC_MESSAGE_ENTRY,
        judge=compare_message_parsers,
    ),
    NativeTarget(
        name="spawn-request",
        family=Family.INTERFACE,
        sources=(
            "native/supervisor/processes/spawn_request.c",
            "native/include/kernel/abi/process.h",
        ),
        max_input_bytes=REQUEST_BYTES,
        seeds=spawn_request_seeds,
        entry=SPAWN_REQUEST_ENTRY,
    ),
    InterpretedTarget(
        name="service-payloads",
        family=Family.INTERFACE,
        sources=("src/kernel_protocol/services",),
        max_input_bytes=MAX_PAYLOAD_BYTES,
        seeds=service_payload_seeds,
        run=decode_service_payload,
        refusals=(KernelError, UnicodeDecodeError),
    ),
    InterpretedTarget(
        name="console-input",
        family=Family.INTERFACE,
        sources=(
            "src/kernel_services/console/discipline.py",
            "src/kernel_services/console/escapes.py",
            "src/kernel_apps/shell/words.py",
        ),
        max_input_bytes=MAX_CONSOLE_BYTES,
        seeds=console_seeds,
        run=type_on_the_console,
    ),
)
