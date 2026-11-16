from kernel_protocol.errors.codes import INVALID_ARGUMENT, TIMED_OUT, UNREACHABLE
from kernel_services.network.counters import ARP_UNRESOLVED, NAMES
from runtime_selftest.checks import Checks
from suites.network.peer import (
    ABSENT,
    BROADCAST,
    GUEST,
    HARDWARE,
    MILLISECOND,
    MTU,
    PEER,
    PREFIX,
    REMOTE,
    SECOND,
)
from suites.network.platform import NetworkSystem
from suites.support.expectations import error_code
from suites.support.reporting import Context

LARGE_ECHO_BYTES = 1024
OVERSIZED_ECHO_BYTES = 1025


def counter(network, name: str) -> int:
    return network.status().counters[NAMES.index(name)]


def run(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    status = network.status()
    checks.require(
        status.address == GUEST
        and status.prefix == PREFIX
        and status.gateway == PEER
        and status.mtu == MTU
        and status.hardware == HARDWARE
        and status.is_linked,
        "the interface reports the static configuration it was started with",
    )
    checks.require(
        len(status.counters) == len(NAMES), "the status carries every counter of the stack"
    )
    checks.require(network.echo(PEER, 2 * SECOND) > 0, "the external stack answers an echo request")
    neighbors = network.neighbors()
    checks.require(
        len(neighbors) == 1 and neighbors[0][0] == PEER and len(neighbors[0][1]) == 6,
        "the peer was resolved and is the only neighbor",
    )
    checks.require(
        network.echo(PEER, 2 * SECOND, LARGE_ECHO_BYTES) > 0,
        "an echo carries up to its documented size",
    )
    checks.require(
        error_code(network.echo, PEER, SECOND, OVERSIZED_ECHO_BYTES) == INVALID_ARGUMENT
        and error_code(network.echo, BROADCAST, SECOND) == INVALID_ARGUMENT
        and error_code(network.echo, 0, SECOND) == INVALID_ARGUMENT,
        "an echo larger than the limit or to no station is refused",
    )
    unresolved = counter(network, ARP_UNRESOLVED)
    checks.require(
        error_code(network.echo, ABSENT, 10 * SECOND) == UNREACHABLE,
        "a station that never answers resolution is reported unreachable",
    )
    checks.require(
        counter(network, ARP_UNRESOLVED) == unresolved + 1,
        "the abandoned resolution is counted",
    )
    checks.require(
        error_code(network.echo, REMOTE, 300 * MILLISECOND) == TIMED_OUT,
        "an echo that gets no answer ends at its deadline",
    )
    checks.require(network.echo(PEER, 2 * SECOND) > 0, "the peer still answers afterwards")
