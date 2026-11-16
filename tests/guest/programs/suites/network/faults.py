from kernel_client import capabilities, devices, ipc
from kernel_protocol.errors.codes import INVALID_HANDLE, PEER_CLOSED, TIMED_OUT
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.network import ACCESS_CONNECT
from kernel_services.network.counters import (
    ARP_MALFORMED,
    FRAGMENTS_INVALID,
    FRAMES_MALFORMED,
    ICMP_MALFORMED,
    IPV4_BAD_CHECKSUM,
    IPV4_MALFORMED,
    IPV4_OPTIONS,
    NAMES,
    TCP_BACKLOG_FULL,
    TCP_BAD_CHECKSUM,
    TCP_MALFORMED,
    TCP_RETRANSMITTED,
    UDP_BAD_CHECKSUM,
    UDP_MALFORMED,
)
from runtime_selftest.checks import Checks
from suites.network.listener_case import echo_until_end
from suites.network.peer import ECHO_PORT, MILLISECOND, PEER, SECOND
from suites.network.platform import NetworkSystem, run_with_network
from suites.network.streams import receive_exactly, stream_part
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.reporting import Context

FLOOD_PORT = 8082
FLOOD_BACKLOG = 4
WAITER = "suites.network.waiter"
MALFORMED_COUNTERS = (
    FRAMES_MALFORMED,
    ARP_MALFORMED,
    IPV4_MALFORMED,
    IPV4_BAD_CHECKSUM,
    IPV4_OPTIONS,
    FRAGMENTS_INVALID,
    ICMP_MALFORMED,
    UDP_MALFORMED,
    UDP_BAD_CHECKSUM,
    TCP_MALFORMED,
    TCP_BAD_CHECKSUM,
)
BLACKOUT_BLOCKS = 32
POLL = 0


def counters(network) -> list[int]:
    return network.status().counters


def value(network, name: str) -> int:
    return counters(network)[NAMES.index(name)]


def all_counted(network, before: list[int]) -> bool:
    after = counters(network)
    return all(after[NAMES.index(name)] > before[NAMES.index(name)] for name in MALFORMED_COUNTERS)


def malformed(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    checks.require(network.echo(PEER, 2 * SECOND) > 0, "the peer answers before the traffic")
    before = counters(network)
    print("network: fault=malformed-traffic state=ready")
    checks.require(
        context.wait_for(lambda: all_counted(network, before)),
        "every kind of malformed packet was counted by its parser",
    )
    status = network.status()
    checks.require(
        status.sockets == 0 and status.buffered_bytes == 0,
        "malformed packets left no socket and no buffer behind",
    )
    checks.require(network.echo(PEER, 2 * SECOND) > 0, "the service still answers afterwards")


def flood(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    listener = network.stream()
    listener.bind(FLOOD_PORT)
    listener.listen(FLOOD_BACKLOG)
    refused = value(network, TCP_BACKLOG_FULL)
    print(f"network: fault=connection-flood state=ready port={FLOOD_PORT}")
    checks.require(
        context.wait_for(lambda: value(network, TCP_BACKLOG_FULL) > refused),
        "connection requests beyond the backlog are refused and counted",
    )
    status = network.status()
    checks.require(
        status.connections <= FLOOD_BACKLOG and status.buffered_bytes == 0,
        "half-open connections stay inside the backlog and hold no buffers",
    )
    checks.require(
        error_code(listener.accept, 300 * MILLISECOND) == TIMED_OUT,
        "a connection that never completes is not handed to the application",
    )
    listener.close()
    checks.require(
        context.wait_for(lambda: network.status().connections == 0),
        "closing the listener drops the half-open connections",
    )
    listener = network.stream()
    listener.bind(FLOOD_PORT)
    listener.listen(FLOOD_BACKLOG)
    print(f"network: fault=connection-flood state=over port={FLOOD_PORT}")
    connection, address, _port = listener.accept(30 * SECOND)
    echoed = echo_until_end(connection)
    connection.finish()
    connection.close()
    listener.close()
    checks.require(address == PEER and echoed > 0, "a real peer connects once the flood is over")
    checks.require(
        context.wait_for(lambda: network.status().connections == 0),
        "the answered connection ends before the next fault begins",
    )


def blackout(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    stream = network.stream()
    stream.connect(PEER, ECHO_PORT, 5 * SECOND)
    retransmitted = value(network, TCP_RETRANSMITTED)
    print("network: fault=link-blackout state=ready")
    context.pause(300 * MILLISECOND)
    message = stream_part(51, 0, BLACKOUT_BLOCKS)
    stream.send_all(message, 30 * SECOND)
    checks.require(
        receive_exactly(stream, len(message)) == message,
        "the transfer completes once the link carries frames again",
    )
    checks.require(
        value(network, TCP_RETRANSMITTED) > retransmitted,
        "the bytes lost in the dark were retransmitted",
    )
    stream.close()
    checks.require(network.echo(PEER, 2 * SECOND) > 0, "connectivity returned")
    checks.require(
        context.wait_for(lambda: network.status().connections == 0),
        "the closed connection ends once the link carries frames again",
    )


def device_reset(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    checks.require(network.echo(PEER, 2 * SECOND) > 0, "the peer answers before the reset")
    resets = network.status().resets
    devices.reset(system.inventory.network)
    checks.require(
        context.wait_for(lambda: network.status().resets > resets),
        "the driver notices the lost device and resets it",
    )
    checks.require(
        context.wait_for(lambda: error_code(network.echo, PEER, SECOND) == 0),
        "connectivity returns after the device was reset",
    )
    checks.require(network.status().is_linked, "the link is reported up again")


def service_restart(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    endpoint = system.endpoint()
    identity, access = network.restrict(ACCESS_CONNECT)
    connected = ipc.create_endpoint()
    child = children.start(
        context.system,
        WAITER,
        grants=((endpoint, RIGHT_SEND), (access, RIGHT_SEND), (connected, RIGHT_SEND)),
    )
    checks.require(
        context.wait_for(lambda: error_code(ipc.receive, connected, POLL) == 0)
        and network.status().connections == 1,
        "a client holds a connection and waits on it",
    )
    capabilities.close(connected)
    capabilities.close(access)
    checks.require(identity != 0, "the service named the access it issued")
    checks.require(system.crash_network(), "the supervisor restarts the service that died")
    checks.require(
        children.finish(child) == EXITED_CLEANLY,
        "the waiting client is told that the service went away",
    )
    fresh = system.network()
    checks.require(
        fresh.instance != network.instance, "the new instance of the service names itself apart"
    )
    checks.require(
        error_code(network.status) in (INVALID_HANDLE, PEER_CLOSED),
        "sessions of the instance before the restart are refused",
    )
    checks.require(
        fresh.status().connections == 0 and fresh.status().sockets == 0,
        "the restarted service starts without the connections of the old one",
    )
    checks.require(fresh.echo(PEER, 2 * SECOND) > 0, "the restarted service reaches the peer")


CASES = (
    ("malformed-traffic", malformed),
    ("connection-flood", flood),
    ("link-blackout", blackout),
    ("device-reset", device_reset),
    ("service-restart-with-a-waiting-client", service_restart),
)


def main() -> bool:
    return run_with_network("network-faults", CASES)
