import _probe

from kernel_client import capabilities, ipc, memory
from kernel_protocol.errors.codes import BAD_ADDRESS
from kernel_protocol.identity.rights import RIGHT_MAP, RIGHT_READ, RIGHT_SEND, RIGHT_WRITE
from kernel_protocol.syscalls.numbers import DEBUG_WRITE
from kernel_protocol.wire.message import Message
from runtime_selftest.checks import Checks
from suites.capabilities.subject import SECRET
from suites.support import children, raw
from suites.support.expectations import EXITED_CLEANLY
from suites.support.layout import PAGE_BYTES, WORD_BYTES
from suites.support.reporting import Context

SUBJECT = "suites.capabilities.subject"
PROCEED_OPERATION = 1
NO_FLAGS = 0
BORROWED_RIGHTS = RIGHT_READ | RIGHT_MAP


def check_revoked_borrower(context: Context, checks: Checks, buffer: int) -> None:
    reports = ipc.create_endpoint()
    borrower = children.start(
        context.system,
        SUBJECT,
        b"borrower",
        grants=((reports, RIGHT_SEND), (buffer, BORROWED_RIGHTS)),
    )
    resume = ipc.receive(reports).transferred
    checks.require(capabilities.revoke(buffer) == 1, "the borrowed capability is revoked")
    ipc.send(resume, Message(PROCEED_OPERATION, NO_FLAGS, 0, b""))
    checks.require(
        children.finish(borrower) == EXITED_CLEANLY,
        "revocation removes the mapping made through the capability",
    )
    capabilities.close(resume)
    capabilities.close(reports)


def check_last_capability(checks: Checks) -> None:
    buffer = memory.create_buffer(PAGE_BYTES)
    status, address, _length = raw.map_buffer(buffer, RIGHT_READ | RIGHT_WRITE)
    checks.require(status == 0 and _probe.load(address) == 0, "the owner maps its buffer")
    capabilities.close(buffer)
    checks.require(
        raw.call(DEBUG_WRITE, address, WORD_BYTES) == -BAD_ADDRESS,
        "a mapping does not outlive the last capability that allows it",
    )


def run(context: Context, checks: Checks) -> None:
    buffer = memory.create_buffer(PAGE_BYTES)
    mapping = memory.Mapping(buffer, True)
    mapping.write(0, SECRET)
    check_revoked_borrower(context, checks, buffer)
    checks.require(
        mapping.read(0, len(SECRET)) == SECRET, "the owner keeps its mapping and its content"
    )
    reader = capabilities.derive(buffer, BORROWED_RIGHTS)
    capabilities.close(reader)
    checks.require(
        mapping.read(0, len(SECRET)) == SECRET,
        "closing a weaker capability leaves a mapping the owner may still hold",
    )
    mapping.unmap()
    capabilities.close(buffer)
    check_last_capability(checks)
