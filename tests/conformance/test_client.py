import pytest

from doubles.native_process import Delivery, NativeProcess
from kernel_client import calls, capabilities, ipc, processes, system
from kernel_protocol.errors.codes import ACCESS_DENIED, LIMIT_EXCEEDED, TIMED_OUT, KernelError
from kernel_protocol.identity.rights import (
    INSPECT_DEPTH_SHIFT,
    INSPECT_RIGHTS_SHIFT,
    OBJECT_ENDPOINT,
    RIGHT_SEND,
)
from kernel_protocol.processes.status import COUNTERS, WAIT_REASON_FAULT, WAIT_REASON_SHIFT
from kernel_protocol.syscalls.numbers import (
    CAPABILITY_CLOSE,
    CAPABILITY_DERIVE,
    CAPABILITY_INSPECT,
    CAPABILITY_REVOKE,
    CLOCK_NOW,
    DEADLINE_NEVER,
    ENDPOINT_CREATE,
    PROCESS_INTERRUPT,
    PROCESS_KILL,
    PROCESS_WAIT,
    PROCESS_YIELD,
)
from kernel_protocol.wire.message import FLAG_REPLY, Message
from kernel_protocol.wire.spawn import encode_spawn_request

SYSTEM = 0x1000001
ENDPOINT = 0x1000002
DERIVED = 0x1000003
CHILD = 0x1000004
REPLY = 0x1000005
PROGRAM = "kernel_services.echo.main"
REQUEST = Message(7, 0, 0x1122, b"ping")


def refusal(operation, *arguments) -> int:
    with pytest.raises(KernelError) as raised:
        operation(*arguments)
    return raised.value.code


def test_negative_status_becomes_a_kernel_error_with_its_code(
    native_process: NativeProcess,
) -> None:
    native_process.call_results[ENDPOINT_CREATE] = [-LIMIT_EXCEEDED, ENDPOINT]

    assert refusal(ipc.create_endpoint) == LIMIT_EXCEEDED
    assert ipc.create_endpoint() == ENDPOINT
    assert calls.check(0) == 0


def test_capability_calls_pass_their_arguments_and_unpack_the_answer(
    native_process: NativeProcess,
) -> None:
    inspection = OBJECT_ENDPOINT | RIGHT_SEND << INSPECT_RIGHTS_SHIFT | 2 << INSPECT_DEPTH_SHIFT
    native_process.call_results = {
        CAPABILITY_DERIVE: [DERIVED],
        CAPABILITY_INSPECT: [inspection],
        CAPABILITY_REVOKE: [3],
    }

    assert capabilities.derive(ENDPOINT, RIGHT_SEND) == DERIVED
    assert capabilities.inspect(DERIVED) == (OBJECT_ENDPOINT, RIGHT_SEND, 2)
    assert capabilities.revoke(ENDPOINT) == 3
    capabilities.close(DERIVED)
    assert native_process.calls == [
        (CAPABILITY_DERIVE, ENDPOINT, RIGHT_SEND),
        (CAPABILITY_INSPECT, DERIVED, 0),
        (CAPABILITY_REVOKE, ENDPOINT, 0),
        (CAPABILITY_CLOSE, DERIVED, 0),
    ]


def test_spawn_sends_the_encoded_request_and_returns_the_process(
    native_process: NativeProcess,
) -> None:
    grants = ((ENDPOINT, RIGHT_SEND),)
    native_process.spawn_results = [CHILD, -ACCESS_DENIED]

    assert processes.spawn(SYSTEM, PROGRAM, b"go", 3, 0x40000, 0x1000, grants) == CHILD
    assert refusal(processes.spawn, SYSTEM, PROGRAM) == ACCESS_DENIED
    assert native_process.spawned == [
        (SYSTEM, encode_spawn_request(PROGRAM, b"go", 3, 0x40000, 0x1000, grants)),
        (SYSTEM, encode_spawn_request(PROGRAM, b"", processes.DEFAULT_PRIORITY, 0, 0, ())),
    ]


def test_process_calls_pass_the_handle_and_split_the_wait_status(
    native_process: NativeProcess,
) -> None:
    native_process.call_results = {
        PROCESS_WAIT: [(WAIT_REASON_FAULT << WAIT_REASON_SHIFT) | 13],
        CLOCK_NOW: [123456789],
    }

    assert processes.wait(CHILD) == (WAIT_REASON_FAULT, 13)
    assert processes.clock() == 123456789
    processes.kill(CHILD)
    processes.interrupt(CHILD)
    processes.yield_now()
    assert native_process.calls == [
        (PROCESS_WAIT, CHILD, DEADLINE_NEVER),
        (CLOCK_NOW, 0, 0),
        (PROCESS_KILL, CHILD, 0),
        (PROCESS_INTERRUPT, CHILD, 0),
        (PROCESS_YIELD, 0, 0),
    ]


def test_startup_exposes_what_the_parent_passed(native_process: NativeProcess) -> None:
    native_process.program = PROGRAM
    native_process.argument = b"first second"
    native_process.handles = (SYSTEM, ENDPOINT)
    native_process.identity = 9

    startup = processes.Startup()

    assert (startup.program, startup.argument) == (PROGRAM, b"first second")
    assert (startup.handles, startup.identity) == ((SYSTEM, ENDPOINT), 9)


def test_send_encodes_the_message_and_passes_transfer_and_deadline(
    native_process: NativeProcess,
) -> None:
    ipc.send(ENDPOINT, REQUEST, transfer=DERIVED, deadline=99)
    ipc.send(ENDPOINT, REQUEST)

    endpoint, message, transfer, deadline = native_process.sent[0]
    assert (endpoint, transfer, deadline) == (ENDPOINT, DERIVED, 99)
    assert (message.operation, message.correlation, message.payload) == (7, 0x1122, b"ping")
    assert native_process.sent[1][2:] == (ipc.NO_TRANSFER, DEADLINE_NEVER)


def test_receive_decodes_the_message_and_keeps_its_metadata(native_process: NativeProcess) -> None:
    native_process.deliveries = [Delivery(REQUEST, sender=5, transferred=DERIVED, reply=REPLY)]

    received = ipc.receive(ENDPOINT)

    assert (received.message.operation, received.message.payload) == (7, b"ping")
    assert (received.sender, received.transferred, received.reply) == (5, DERIVED, REPLY)
    assert refusal(ipc.receive, ENDPOINT, 1) == TIMED_OUT


def test_call_returns_the_response_and_the_capability_that_came_with_it(
    native_process: NativeProcess,
) -> None:
    native_process.responses = [
        Delivery(Message(7, FLAG_REPLY, 0x1122, b"pong"), transferred=DERIVED)
    ]

    response, transferred = ipc.call(ENDPOINT, REQUEST)

    assert (response.payload, response.correlation, transferred) == (b"pong", 0x1122, DERIVED)
    assert native_process.requested[0][0] == ENDPOINT
    assert native_process.requested[0][2:] == (ipc.NO_TRANSFER, DEADLINE_NEVER)
    assert refusal(ipc.call, ENDPOINT, REQUEST) == TIMED_OUT


def test_answer_repeats_the_operation_and_correlation_of_the_request(
    native_process: NativeProcess,
) -> None:
    native_process.deliveries = [Delivery(REQUEST, reply=REPLY)]

    ipc.answer(ipc.receive(ENDPOINT), b"pong")

    reply, message, transfer = native_process.replied[0]
    assert (reply, transfer) == (REPLY, ipc.NO_TRANSFER)
    assert (message.operation, message.flags) == (7, FLAG_REPLY)
    assert (message.correlation, message.payload) == (0x1122, b"pong")


def test_counters_are_returned_and_a_refusal_is_raised(native_process: NativeProcess) -> None:
    native_process.counter_values = tuple(range(COUNTERS))
    assert system.counters(SYSTEM) == tuple(range(COUNTERS))

    native_process.counter_values = -ACCESS_DENIED
    assert refusal(system.counters, SYSTEM) == ACCESS_DENIED
