from kernel_client import capabilities, ipc, memory
from kernel_protocol.errors.codes import BAD_ADDRESS, PEER_CLOSED
from kernel_protocol.identity.rights import RIGHT_READ, RIGHT_SEND, RIGHT_WRITE
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER, DEBUG_WRITE
from kernel_protocol.wire.message import Message, encode_message
from runtime_selftest.checks import Checks
from suites.support import children, raw
from suites.support.expectations import EXITED_CLEANLY, KILLED, error_code
from suites.support.layout import PAGE_BYTES, WORD_BYTES
from suites.support.reporting import Context

OWNER = "suites.memory.owner"
EXECUTIONER = "suites.memory.executioner"
REQUEST = encode_message(Message(1, 0, 1, b""))


def run(context: Context, checks: Checks) -> None:
    registrations = ipc.create_endpoint()
    grants = ((registrations, RIGHT_SEND),)
    owner = children.start(context.system, OWNER, grants=grants)
    buffer = ipc.receive(registrations).transferred
    status, address, length = raw.map_buffer(buffer, RIGHT_READ | RIGHT_WRITE)
    checks.require(status == 0 and length == PAGE_BYTES, "the borrower maps the granted buffer")

    executioner = children.start(context.system, EXECUTIONER, grants=grants)
    endpoint = ipc.receive(registrations).transferred
    checks.require(
        raw.call_into(endpoint, REQUEST, address, PAGE_BYTES, owner, DEADLINE_NEVER)
        == -BAD_ADDRESS,
        "a reply into a mapping removed during the call is refused",
    )
    checks.require(
        raw.call(DEBUG_WRITE, address, WORD_BYTES) == -BAD_ADDRESS,
        "the removed mapping is no longer readable",
    )
    checks.require(
        error_code(memory.Mapping, buffer, False) == PEER_CLOSED,
        "a buffer cannot be mapped after its owner is gone",
    )
    checks.require(children.finish(owner) == KILLED, "the owner was killed during the call")
    checks.require(children.finish(executioner) == EXITED_CLEANLY, "the server finished its reply")
    for handle in (buffer, endpoint, registrations):
        capabilities.close(handle)
