import _process
from kernel_client import capabilities, ipc
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER
from kernel_protocol.wire.message import FLAG_REPLY, HEADER_BYTES, decode_message, encode_message
from runtime_selftest.checks import Checks
from suites.ipc.actors import start_server
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.reporting import Context

CORRELATION = 0x1122334455667788
PAYLOAD = b"correlated"
RESPONSE_CAPACITY = HEADER_BYTES + 64
NO_TRANSFER = 0


def run(context: Context, checks: Checks) -> None:
    registrations = ipc.create_endpoint()
    strict, service = start_server(context, b"strict", registrations)
    response = bytearray(RESPONSE_CAPACITY)
    request = encode_message(plain(OPERATION_REQUEST, CORRELATION, PAYLOAD))
    status = _process.request(service, request, response, NO_TRANSFER, DEADLINE_NEVER)[0]
    checks.require(status == HEADER_BYTES + len(PAYLOAD), "only the valid reply is delivered")
    reply = decode_message(bytes(response[:status]))
    checks.require(
        reply.flags == FLAG_REPLY and reply.correlation == CORRELATION and reply.payload == PAYLOAD,
        "the reply carries the correlation of its request",
    )
    checks.require(
        children.finish(strict) == EXITED_CLEANLY,
        "wrong correlation, missing flag, oversized and repeated replies are refused",
    )
    capabilities.close(service)
    capabilities.close(registrations)
