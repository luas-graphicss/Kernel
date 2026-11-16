from kernel_client import capabilities, ipc, services
from kernel_protocol.errors.codes import KernelError
from kernel_protocol.services.block import OPERATION_EVICT as BLOCK_EVICT
from kernel_protocol.services.block import encode_client
from kernel_protocol.services.files import OPERATION_ROOT
from kernel_services.init import lifecycle
from kernel_services.init.devices import NO_DEVICE, Inventory, discover
from kernel_services.init.lifecycle import NO_ENDPOINT, Running
from kernel_services.init.manifest import (
    BLOCK,
    BLOCKS,
    CONSOLE,
    DEVICE,
    ENTROPY,
    FILESYSTEM,
    KNOWN_GRANTS,
    STORAGE,
    Service,
)

ROLE_SEPARATOR = b","
NO_NAMESPACE = 0


def announce(running: Running, detail: str = "") -> None:
    state = "ready" if running.endpoint != NO_ENDPOINT else "failed"
    print(f"init: service={running.service.program}{detail} {state}")


class ServiceSystem:
    def __init__(self, system: int, identity: int) -> None:
        self._system = system
        self._identity = identity
        self._registration = ipc.create_endpoint()
        self.inventory: Inventory = discover(system)
        self.console: Running | None = None
        self.entropy: Running | None = None
        self.blocks: dict[bytes, Running] = {}
        self.block_devices: dict[bytes, int] = {}
        self.filesystem: Running | None = None
        self.namespace = NO_NAMESPACE

    def start(self) -> bool:
        started = True
        if self.inventory.serial != NO_DEVICE:
            self.console = self._start_driver(CONSOLE, self.inventory.serial)
            announce(self.console)
            started = self.console.endpoint != NO_ENDPOINT
        if self.inventory.entropy != NO_DEVICE:
            self.entropy = self._start_driver(ENTROPY, self.inventory.entropy)
            announce(self.entropy)
            started = self.entropy.endpoint != NO_ENDPOINT and started
        for device in self.inventory.blocks:
            started = self._start_block(device) and started
        return self.start_filesystem() and started

    def start_filesystem(self) -> bool:
        names = []
        grants = []
        for mount, device in STORAGE:
            block = self.blocks.get(device)
            if block is not None:
                names.append(mount)
                grants.append((block.endpoint, KNOWN_GRANTS[BLOCKS]))
        role = ROLE_SEPARATOR.join(names)
        running = self._start(FILESYSTEM, tuple(grants), role)
        self.filesystem = running
        announce(running)
        if running.endpoint == NO_ENDPOINT:
            return False
        _payload, self.namespace = services.call(running.endpoint, OPERATION_ROOT)
        return True

    def stop_filesystem(self) -> bool:
        running = self.filesystem
        if running is None:
            return True
        if self.namespace != NO_NAMESPACE:
            capabilities.close(self.namespace)
            self.namespace = NO_NAMESPACE
        self.filesystem = None
        stopped = lifecycle.stop(running)
        for device in sorted(self.blocks):
            self._evict(self.blocks[device], running.identity)
        return stopped

    def restart_filesystem(self) -> bool:
        self.stop_filesystem()
        return self.start_filesystem()

    def restart_block(self, device: bytes) -> bool:
        self.stop_filesystem()
        lifecycle.stop(self.blocks.pop(device))
        restarted = self._start_block(self.block_devices[device])
        return self.start_filesystem() and restarted

    def stop(self) -> bool:
        stopped = self._report(self.filesystem, self.stop_filesystem())
        for device in sorted(self.blocks):
            stopped = (
                self._report(self.blocks[device], lifecycle.stop(self.blocks[device])) and stopped
            )
        self.blocks = {}
        if self.entropy is not None:
            stopped = self._report(self.entropy, lifecycle.stop(self.entropy)) and stopped
        if self.console is not None:
            stopped = self._report(self.console, lifecycle.stop(self.console)) and stopped
        capabilities.close(self._registration)
        return stopped

    def _start_block(self, device: int) -> bool:
        running = self._start_driver(BLOCK, device)
        name = running.announcement
        if running.endpoint == NO_ENDPOINT or name == b"" or name in self.blocks:
            announce(running)
            lifecycle.stop(running)
            return False
        self.blocks[name] = running
        self.block_devices[name] = device
        label = str(name, "utf-8")
        announce(running, f" device={label}")
        return True

    def _start_driver(self, service: Service, device: int) -> Running:
        return self._start(service, ((device, KNOWN_GRANTS[DEVICE]),), b"")

    def _start(self, service: Service, grants: tuple[tuple[int, int], ...], role: bytes) -> Running:
        return lifecycle.start(
            self._system, self._registration, self._identity, service, grants, role
        )

    def _evict(self, block: Running, client: int) -> None:
        try:
            services.call(block.endpoint, BLOCK_EVICT, encode_client(client))
        except KernelError:
            return

    def _report(self, running: Running | None, stopped: bool) -> bool:
        if running is not None:
            verdict = "0" if stopped else "failed"
            print(f"init: service={running.service.program} exit={verdict}")
        return stopped
