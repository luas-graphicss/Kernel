from kernel_client import capabilities, ipc
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.wire.message import Message
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.raw import word
from suites.support.reporting import Context

SUBJECT = "suites.capabilities.subject"
FORGERY_OPERATION = 1
NO_FLAGS = 0


def run(context: Context, checks: Checks) -> None:
    checks.require(
        children.run(context.system, SUBJECT, b"bare") == EXITED_CLEANLY,
        "a process started without grants holds no capability",
    )
    registrations = ipc.create_endpoint()
    forger = children.start(
        context.system, SUBJECT, b"forger", grants=((registrations, RIGHT_SEND),)
    )
    target = ipc.receive(registrations).transferred
    claimed = word(context.system) + word(registrations)
    ipc.send(target, Message(FORGERY_OPERATION, NO_FLAGS, 0, claimed))
    checks.require(
        children.finish(forger) == EXITED_CLEANLY,
        "handle values copied into a payload give no authority",
    )
    capabilities.close(target)
    capabilities.close(registrations)
