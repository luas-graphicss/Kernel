from kernel_client import capabilities, ipc
from kernel_protocol.errors.codes import OK
from kernel_protocol.identity.rights import RIGHT_DELEGATE, RIGHT_SEND
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.reporting import Context

SUBJECT = "suites.capabilities.subject"
DELEGABLE_SEND = RIGHT_SEND | RIGHT_DELEGATE


def is_valid(handle: int) -> bool:
    return error_code(capabilities.inspect, handle) == OK


def check_tree(checks: Checks, root: int) -> None:
    left = capabilities.derive(root, DELEGABLE_SEND)
    right = capabilities.derive(root, DELEGABLE_SEND)
    leaves = [capabilities.derive(left, RIGHT_SEND) for _ in range(2)]
    checks.require(capabilities.revoke(left) == len(leaves), "revocation counts the descendants")
    checks.require(not any(is_valid(leaf) for leaf in leaves), "every descendant stops being valid")
    checks.require(
        is_valid(left) and is_valid(right), "the revoked capability and its siblings remain"
    )
    checks.require(capabilities.revoke(left) == 0, "a second revocation finds nothing")

    orphan = capabilities.derive(right, RIGHT_SEND)
    capabilities.close(right)
    checks.require(is_valid(orphan), "closing a capability keeps what was derived from it")
    checks.require(
        capabilities.revoke(root) == 2 and not is_valid(orphan) and not is_valid(left),
        "the root still reaches descendants whose parent was closed",
    )


def check_other_process(context: Context, checks: Checks, root: int) -> None:
    subject = children.start(context.system, SUBJECT, b"sender", grants=((root, DELEGABLE_SEND),))
    ipc.receive(root)
    checks.require(
        capabilities.revoke(root) >= 1, "revocation reaches capabilities of another process"
    )
    checks.require(
        children.finish(subject) == EXITED_CLEANLY,
        "the other process loses the capability while it is using it",
    )


def run(context: Context, checks: Checks) -> None:
    root = ipc.create_endpoint()
    check_tree(checks, root)
    check_other_process(context, checks, root)
    capabilities.close(root)
