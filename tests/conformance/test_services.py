import importlib.util

import pytest

from doubles.native_process import Delivery, NativeProcess
from kernel_core.bootstrap import INIT_PRIORITY, INIT_PROGRAM
from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import (
    PRIORITY_LEVELS,
    WAIT_REASON_EXIT,
    WAIT_REASON_KILLED,
    WAIT_REASON_SHIFT,
)
from kernel_protocol.syscalls.numbers import CAPABILITY_CLOSE, ENDPOINT_CREATE, PROCESS_WAIT
from kernel_protocol.wire.message import FLAG_REPLY, Message
from kernel_protocol.wire.spawn import PAGE_BYTES, encode_spawn_request, name_is_valid
from kernel_services.echo import main as echo
from kernel_services.echo.protocol import OPERATION_ECHO, OPERATION_REGISTER, OPERATION_STOP
from kernel_services.init import main as init
from kernel_services.init.manifest import KNOWN_GRANTS, SERVICES, Service

SYSTEM = 0x1000001
REGISTRATION = 0x1000002
SERVICE_PROCESS = 0x1000003
SERVICE_ENDPOINT = 0x1000004
REPLY = 0x1000010
ECHO_PROGRAM = "kernel_services.echo.main"
EXITED_CLEANLY = WAIT_REASON_EXIT << WAIT_REASON_SHIFT
REGISTERED = Delivery(Message(OPERATION_REGISTER, 0, 1, b""), transferred=SERVICE_ENDPOINT)
ECHOED = Delivery(Message(OPERATION_ECHO, FLAG_REPLY, init.PROBE_CORRELATION, init.PROBE_PAYLOAD))
STOPPED = Delivery(Message(OPERATION_STOP, FLAG_REPLY, init.PROBE_CORRELATION, b""))


def run_init(
    native: NativeProcess, announced: Delivery, responses: list[Delivery], status: int
) -> bool:
    native.handles = (SYSTEM,)
    native.call_results = {ENDPOINT_CREATE: [REGISTRATION], PROCESS_WAIT: [status]}
    native.spawn_results = [SERVICE_PROCESS]
    native.deliveries = [announced]
    native.responses = responses
    return init.main()


def closed(native: NativeProcess) -> list[int]:
    return [first for number, first, _second in native.calls if number == CAPABILITY_CLOSE]


def test_service_asking_for_an_unknown_capability_is_refused() -> None:
    with pytest.raises(KernelError) as raised:
        Service(ECHO_PROGRAM, 2, 0x40000, ("registration", "disk"))

    assert raised.value.code == INVALID_ARGUMENT


def test_every_service_of_the_manifest_can_be_started_by_init() -> None:
    assert name_is_valid(INIT_PROGRAM)
    for service in SERVICES:
        assert name_is_valid(service.program)
        assert importlib.util.find_spec(service.program) is not None
        assert INIT_PRIORITY <= service.priority < PRIORITY_LEVELS
        assert service.heap_bytes % PAGE_BYTES == 0
        assert set(service.grants) <= set(KNOWN_GRANTS)


def test_init_starts_probes_and_stops_each_service(
    native_process: NativeProcess, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_init(native_process, REGISTERED, [ECHOED, STOPPED], EXITED_CLEANLY) is True

    grants = ((REGISTRATION, RIGHT_SEND),)
    assert native_process.spawned == [
        (SYSTEM, encode_spawn_request(ECHO_PROGRAM, b"", 2, 0x40000, 0, grants))
    ]
    assert [
        message.operation for _endpoint, message, _transfer, _deadline in native_process.requested
    ] == [
        OPERATION_ECHO,
        OPERATION_STOP,
    ]
    assert closed(native_process) == [SERVICE_ENDPOINT, SERVICE_PROCESS, REGISTRATION]
    assert capsys.readouterr().out.splitlines() == [
        "init: runtime=micropython privilege=user",
        f"init: service={ECHO_PROGRAM} ready",
        f"init: service={ECHO_PROGRAM} echo=ok",
        f"init: service={ECHO_PROGRAM} exit=0",
    ]


def test_init_fails_when_the_answer_is_not_what_it_sent(
    native_process: NativeProcess, capsys: pytest.CaptureFixture[str]
) -> None:
    altered = Delivery(Message(OPERATION_ECHO, FLAG_REPLY, init.PROBE_CORRELATION, b"other"))

    assert run_init(native_process, REGISTERED, [altered, STOPPED], EXITED_CLEANLY) is False
    assert f"init: service={ECHO_PROGRAM} echo=failed" in capsys.readouterr().out.splitlines()


def test_init_fails_when_the_service_does_not_register_an_endpoint(
    native_process: NativeProcess, capsys: pytest.CaptureFixture[str]
) -> None:
    unregistered = Delivery(Message(OPERATION_REGISTER, 0, 1, b""))

    assert run_init(native_process, unregistered, [], EXITED_CLEANLY) is False
    assert native_process.requested == []
    assert closed(native_process) == [SERVICE_PROCESS, REGISTRATION]
    assert capsys.readouterr().out.splitlines() == [
        "init: runtime=micropython privilege=user",
        f"init: service={ECHO_PROGRAM} echo=failed",
        f"init: service={ECHO_PROGRAM} exit=0",
    ]


@pytest.mark.parametrize(
    "status",
    [EXITED_CLEANLY | 1, WAIT_REASON_KILLED << WAIT_REASON_SHIFT],
    ids=["status", "killed"],
)
def test_init_fails_when_the_service_does_not_exit_cleanly(
    native_process: NativeProcess, status: int
) -> None:
    assert run_init(native_process, REGISTERED, [ECHOED, STOPPED], status) is False


def test_echo_registers_its_endpoint_then_answers_until_stopped(
    native_process: NativeProcess,
) -> None:
    native_process.handles = (REGISTRATION,)
    native_process.call_results = {ENDPOINT_CREATE: [SERVICE_ENDPOINT]}
    native_process.deliveries = [
        Delivery(Message(OPERATION_ECHO, 0, 1, b"no reply expected")),
        Delivery(Message(OPERATION_ECHO, 0, 2, b"ping"), reply=REPLY),
        Delivery(Message(99, 0, 3, b"unknown"), reply=REPLY + 1),
        Delivery(Message(OPERATION_STOP, 0, 4, b""), reply=REPLY + 2),
    ]

    assert echo.main() is True

    endpoint, registration, transferred, _deadline = native_process.sent[0]
    assert (endpoint, registration.operation, transferred) == (
        REGISTRATION,
        OPERATION_REGISTER,
        SERVICE_ENDPOINT,
    )
    assert [
        (reply, message.operation, message.correlation, message.payload)
        for reply, message, _transfer in native_process.replied
    ] == [
        (REPLY, OPERATION_ECHO, 2, b"ping"),
        (REPLY + 1, 99, 3, b""),
        (REPLY + 2, OPERATION_STOP, 4, b""),
    ]
