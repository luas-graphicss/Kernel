from kernel_client import sockets
from kernel_client.processes import Startup
from kernel_protocol.configuration.model import ENTROPY, NETWORK, Interface, ServicePolicy
from kernel_services.manager.devices import discover
from kernel_services.manager.processes import Launcher, terminate
from kernel_services.manager.units.drivers import ENTROPY_PROGRAM, DriverUnit
from kernel_services.manager.units.network import NetworkUnit
from suites.network.peer import GUEST, MTU, PEER, PREFIX, SECOND
from suites.support.reporting import run_suite

WINDOW = 60 * SECOND
ENTROPY_POLICY = ServicePolicy(ENTROPY, (), 0, WINDOW, 2, 0x40000)
NETWORK_POLICY = ServicePolicy(NETWORK, (ENTROPY,), 0, WINDOW, 2, 0x400000)


class NetworkSystem:
    def __init__(self, system: int, identity: int) -> None:
        self.system = system
        self.launcher = Launcher(system, identity)
        self.inventory = discover(system)
        self.entropy = DriverUnit(ENTROPY, ENTROPY_PROGRAM, self.launcher, self.inventory.entropy)
        self.unit = NetworkUnit(
            self.launcher, self.inventory.network, self.entropy, Interface(GUEST, PREFIX, PEER, MTU)
        )

    def start(self) -> bool:
        return self.entropy.start(ENTROPY_POLICY) and self.unit.start(NETWORK_POLICY)

    def stop(self) -> bool:
        stopped = self.unit.stop()
        return self.entropy.stop() and stopped

    def crash_network(self) -> bool:
        started = self.unit.started
        if started is not None:
            terminate(started.process)
        self.unit.collect()
        return self.unit.start(NETWORK_POLICY)

    def network(self) -> sockets.Network:
        session = self.unit.session
        if session is None:
            raise ValueError("the network service is not running")
        return session

    def endpoint(self) -> int:
        return self.unit.endpoint()


def bind(run, system: NetworkSystem):
    def bound(context, checks) -> None:
        run(system, context, checks)

    return bound


def run_with_network(suite: str, cases) -> bool:
    startup = Startup()
    system = NetworkSystem(startup.handles[0], startup.identity)
    started = system.start()
    if not started:
        print(f"test: suite={suite} case=network-service result=failed")
    passed = started and run_suite(suite, [(name, bind(run, system)) for name, run in cases])
    return system.stop() and passed
