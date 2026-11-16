from kernel_client import capabilities, ipc
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    LIMIT_EXCEEDED,
)
from kernel_protocol.identity.rights import (
    CAPABILITY_MAX_DEPTH,
    OBJECT_ENDPOINT,
    OBJECT_SYSTEM,
    RIGHT_ADMIN,
    RIGHT_DELEGATE,
    RIGHT_READ,
    RIGHT_RECEIVE,
    RIGHT_SEND,
)
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.reporting import Context

ENDPOINT_RIGHTS = RIGHT_SEND | RIGHT_RECEIVE | RIGHT_DELEGATE
SYSTEM_RIGHTS = RIGHT_ADMIN | RIGHT_READ | RIGHT_DELEGATE
DELEGABLE_SEND = RIGHT_SEND | RIGHT_DELEGATE
UNKNOWN_RIGHT = 0x80
RIGHTS_BEYOND_THE_FIELD = 1 << 32


def check_refusals(checks: Checks, endpoint: int, sender: int) -> None:
    refused = (
        ("a right the source lacks", endpoint, RIGHT_SEND | RIGHT_READ, ACCESS_DENIED),
        ("the receive right", endpoint, RIGHT_RECEIVE, ACCESS_DENIED),
        ("a source without the delegate right", sender, RIGHT_SEND, ACCESS_DENIED),
        ("no right at all", endpoint, 0, INVALID_ARGUMENT),
        ("an unknown right", endpoint, UNKNOWN_RIGHT, INVALID_ARGUMENT),
        ("rights wider than the field", endpoint, RIGHTS_BEYOND_THE_FIELD, INVALID_ARGUMENT),
    )
    for description, source, rights, code in refused:
        checks.require(
            error_code(capabilities.derive, source, rights) == code,
            f"deriving {description} is refused",
        )


def check_depth(checks: Checks, endpoint: int) -> None:
    chain = [endpoint]
    for _ in range(CAPABILITY_MAX_DEPTH):
        chain.append(capabilities.derive(chain[-1], DELEGABLE_SEND))
    checks.require(
        capabilities.inspect(chain[-1]) == (OBJECT_ENDPOINT, DELEGABLE_SEND, CAPABILITY_MAX_DEPTH),
        "each derivation is one level deeper",
    )
    checks.require(
        error_code(capabilities.derive, chain[-1], RIGHT_SEND) == LIMIT_EXCEEDED,
        "delegation stops at the depth limit",
    )
    checks.require(
        capabilities.revoke(endpoint) == CAPABILITY_MAX_DEPTH + 1,
        "revoking the root removes the whole chain",
    )
    checks.require(
        all(error_code(capabilities.inspect, link) == INVALID_HANDLE for link in chain[1:]),
        "no link of a revoked chain stays valid",
    )


def run(context: Context, checks: Checks) -> None:
    endpoint = ipc.create_endpoint()
    sender = capabilities.derive(endpoint, RIGHT_SEND)
    checks.require(
        capabilities.inspect(context.system) == (OBJECT_SYSTEM, SYSTEM_RIGHTS, 0),
        "the first process holds the system capability",
    )
    checks.require(
        capabilities.inspect(endpoint) == (OBJECT_ENDPOINT, ENDPOINT_RIGHTS, 0),
        "a new endpoint carries its creation rights",
    )
    checks.require(
        capabilities.inspect(sender) == (OBJECT_ENDPOINT, RIGHT_SEND, 1),
        "a derived capability carries only the requested rights",
    )
    check_refusals(checks, endpoint, sender)
    check_depth(checks, endpoint)
    capabilities.close(endpoint)
