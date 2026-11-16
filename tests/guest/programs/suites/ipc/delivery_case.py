import _process
from kernel_client import capabilities, ipc, processes
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_HANDLE,
    MESSAGE_TOO_LARGE,
    TIMED_OUT,
)
from kernel_protocol.identity.rights import OBJECT_ENDPOINT, RIGHT_DELEGATE, RIGHT_SEND
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER
from kernel_protocol.wire.message import HEADER_BYTES, MAX_PAYLOAD_BYTES
from runtime_selftest.checks import Checks
from suites.ipc.actors import start_server
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.reporting import Context

PAYLOADS = (b"", b"x", bytes(range(256)) * (MAX_PAYLOAD_BYTES // 256))
TRANSFERRED_RIGHTS = RIGHT_SEND | RIGHT_DELEGATE
NEVER_ISSUED_HANDLE = 0x7F000001
SHORT_STORAGE_BYTES = HEADER_BYTES + 4
SHORT_WAIT_NANOSECONDS = 2000000


def check_round_trips(context: Context, checks: Checks, endpoint: int) -> None:
    for payload in PAYLOADS:
        ipc.send(endpoint, plain(OPERATION_REQUEST, len(payload), payload))
        received = ipc.receive(endpoint)
        checks.require(
            received.message.payload == payload and received.message.correlation == len(payload),
            "a message arrives unchanged",
        )
        checks.require(
            received.sender == context.identity
            and received.transferred == 0
            and received.reply == 0,
            "the kernel names the sender and adds no capability",
        )
    ipc.send(endpoint, plain(OPERATION_REQUEST, 1, b"longer than the buffer"))
    status = _process.receive(endpoint, bytearray(SHORT_STORAGE_BYTES), DEADLINE_NEVER)[0]
    checks.require(status == -MESSAGE_TOO_LARGE, "a buffer that is too small is refused")
    checks.require(
        ipc.receive(endpoint).message.correlation == 1, "the message stays queued for a retry"
    )


def check_transfers(checks: Checks, endpoint: int) -> None:
    offered = ipc.create_endpoint()
    ipc.send(endpoint, plain(OPERATION_REQUEST), offered)
    transferred = ipc.receive(endpoint).transferred
    checks.require(
        transferred != offered
        and capabilities.inspect(transferred) == (OBJECT_ENDPOINT, TRANSFERRED_RIGHTS, 1),
        "a transferred capability arrives derived and without the receive right",
    )
    sender = capabilities.derive(offered, RIGHT_SEND)
    checks.require(
        error_code(ipc.send, endpoint, plain(OPERATION_REQUEST), sender) == ACCESS_DENIED,
        "a capability without the delegate right is not transferred",
    )
    checks.require(
        error_code(ipc.send, endpoint, plain(OPERATION_REQUEST), NEVER_ISSUED_HANDLE)
        == INVALID_HANDLE,
        "a handle that was never issued is not transferred",
    )
    checks.require(
        error_code(ipc.receive, endpoint, processes.clock() + SHORT_WAIT_NANOSECONDS) == TIMED_OUT,
        "a refused transfer queues nothing",
    )
    for handle in (transferred, sender, offered):
        capabilities.close(handle)


def check_reply_transfer(context: Context, checks: Checks, registrations: int) -> None:
    lender, service = start_server(context, b"lender", registrations)
    _response, lent = ipc.call(service, plain(OPERATION_REQUEST))
    checks.require(
        capabilities.inspect(lent) == (OBJECT_ENDPOINT, TRANSFERRED_RIGHTS, 1),
        "a reply carries a capability to the caller",
    )
    checks.require(children.finish(lender) == EXITED_CLEANLY, "the lending server finishes")
    capabilities.close(lent)
    capabilities.close(service)


def run(context: Context, checks: Checks) -> None:
    endpoint = ipc.create_endpoint()
    check_round_trips(context, checks, endpoint)
    check_transfers(checks, endpoint)
    check_reply_transfer(context, checks, endpoint)
    capabilities.close(endpoint)
