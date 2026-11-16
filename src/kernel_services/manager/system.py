from kernel_client import capabilities, ipc, power, processes
from kernel_protocol.configuration.errors import ConfigurationError
from kernel_protocol.configuration.model import (
    CONSOLE,
    ENTROPY,
    NETWORK,
    SHELL,
    STORAGE,
    Configuration,
    ServicePolicy,
)
from kernel_protocol.errors.codes import TIMED_OUT, KernelError
from kernel_protocol.services.control import SYSTEM_STATE_NAMES
from kernel_protocol.system.power import POWER_ACTION_RESTART
from kernel_services.manager.applications import Applications
from kernel_services.manager.clients import Clients
from kernel_services.manager.control import NO_REQUEST, ControlService
from kernel_services.manager.devices import NO_DEVICE, Inventory, discover
from kernel_services.manager.journal import report
from kernel_services.manager.processes import Launcher
from kernel_services.manager.resources import Resources
from kernel_services.manager.settings import read_configuration
from kernel_services.manager.supervision import Supervisor
from kernel_services.manager.units.base import Unit
from kernel_services.manager.units.drivers import CONSOLE_PROGRAM, ENTROPY_PROGRAM, DriverUnit
from kernel_services.manager.units.network import NetworkUnit
from kernel_services.manager.units.shell import ShellUnit
from kernel_services.manager.units.storage import StorageUnit

POLL = 0
REQUEST_BATCH = 16
SERVE_SLICE_NANOSECONDS = 50000000
BOOTSTRAP_HEAP_BYTES = 0x200000
BOOTSTRAP_PRIORITY = 2
BOOTSTRAP_WINDOW_NANOSECONDS = 1000000000


class System:
    def __init__(self, system_handle: int, identity: int) -> None:
        self._system = system_handle
        self._launcher = Launcher(system_handle, identity)
        self._inventory: Inventory = discover(system_handle)
        self._control_endpoint = ipc.create_endpoint()
        self._resources = Resources()
        self._clients = Clients(self._resources)
        self._supervisor = Supervisor()
        self._applications = Applications(self._launcher, self._resources)
        self._control = ControlService(
            system_handle, self._supervisor, self._applications, self._resources, self._clients
        )
        self._storage = StorageUnit(self._launcher, self._inventory.blocks)
        self._resources.storage = self._storage

    def run(self) -> bool:
        self._describe_devices()
        configuration = self._bootstrap()
        if configuration is None:
            self._release()
            return False
        self._supervisor.start_all(processes.clock())
        self._report_state()
        while self._control.requested_action == NO_REQUEST:
            self._serve()
            self._keep(processes.clock())
        return self._stop(self._control.requested_action)

    def _describe_devices(self) -> None:
        inventory = self._inventory
        report(
            f"devices serial={1 if inventory.serial != NO_DEVICE else 0} "
            f"entropy={1 if inventory.entropy != NO_DEVICE else 0} "
            f"network={1 if inventory.network != NO_DEVICE else 0} "
            f"block={len(inventory.blocks)}"
        )

    def _bootstrap(self) -> Configuration | None:
        bootstrap = ServicePolicy(
            STORAGE, (), 0, BOOTSTRAP_WINDOW_NANOSECONDS, BOOTSTRAP_PRIORITY, BOOTSTRAP_HEAP_BYTES
        )
        namespace = None
        if self._storage.start(bootstrap):
            namespace = self._storage.namespace
        if namespace is None:
            report("configuration=rejected reason=storage-unavailable subject=boot")
            return None
        try:
            configuration = read_configuration(namespace)
            self._apply(configuration)
        except ConfigurationError as error:
            report(f"configuration=rejected reason={error.reason} subject={error.subject}")
            self._storage.stop()
            return None
        report(
            f"configuration=accepted name={configuration.name} services={len(configuration.order)}"
        )
        return configuration

    def _apply(self, configuration: Configuration) -> None:
        units = self._units(configuration)
        for name in configuration.order:
            self._supervisor.add(units[name], configuration.services[name])
        self._supervisor.arrange(configuration.order)
        self._supervisor.adopt(STORAGE)
        self._applications.configure(configuration.applications)

    def _units(self, configuration: Configuration) -> dict[str, Unit]:
        inventory = self._inventory
        units: dict[str, Unit] = {STORAGE: self._storage}
        console = DriverUnit(CONSOLE, CONSOLE_PROGRAM, self._launcher, inventory.serial)
        entropy = DriverUnit(ENTROPY, ENTROPY_PROGRAM, self._launcher, inventory.entropy)
        units[CONSOLE] = console
        units[ENTROPY] = entropy
        self._resources.console = console
        interface = configuration.interface
        if NETWORK in configuration.services and interface is not None:
            network = NetworkUnit(self._launcher, inventory.network, entropy, interface)
            units[NETWORK] = network
            self._resources.network = network
        if SHELL in configuration.services:
            units[SHELL] = ShellUnit(
                self._launcher, self._control_endpoint, self._clients, configuration.shell
            )
        return units

    def _serve(self) -> None:
        deadline = processes.clock() + SERVE_SLICE_NANOSECONDS
        for _ in range(REQUEST_BATCH):
            try:
                request = ipc.receive(self._control_endpoint, deadline)
            except KernelError as error:
                if error.code != TIMED_OUT:
                    raise
                return
            self._control.arrive(request, processes.clock())
            deadline = POLL

    def _keep(self, now: int) -> None:
        before = self._supervisor.state()
        self._supervisor.check(now)
        self._applications.reap()
        self._control.settle(now)
        if self._supervisor.state() != before:
            self._report_state()

    def _report_state(self) -> None:
        report(f"state={SYSTEM_STATE_NAMES[self._supervisor.state()]}")

    def _stop(self, action: int) -> bool:
        restarts = action == POWER_ACTION_RESTART
        report(f"shutdown=started action={'restart' if restarts else 'shutdown'}")
        stopped = self._applications.stop_all()
        self._control.cancel_waits()
        report(f"shutdown=applications stopped={stopped}")
        clean = self._supervisor.stop_all()
        self._release()
        if restarts:
            power.request_restart(self._system)
        else:
            power.request_shutdown(self._system)
        report(f"shutdown=complete clean={1 if clean else 0}")
        return clean

    def _release(self) -> None:
        capabilities.close(self._control_endpoint)
