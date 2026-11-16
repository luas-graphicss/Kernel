from kernel_client import capabilities, files, services
from kernel_protocol.configuration.model import (
    FILES_READ,
    FILES_READ_WRITE,
    STORAGE,
    ServicePolicy,
)
from kernel_protocol.errors.codes import BAD_STATE, KernelError
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.block import OPERATION_EVICT as BLOCK_EVICT
from kernel_protocol.services.block import encode_client
from kernel_protocol.services.files import (
    NAMESPACE_READ,
    NAMESPACE_WRITE,
    OPERATION_EVICT,
    OPERATION_ROOT,
    encode_size,
)
from kernel_protocol.services.lifecycle import encode_supervisor
from kernel_services.manager import processes
from kernel_services.manager.devices import DRIVER_RIGHTS
from kernel_services.manager.processes import NO_ENDPOINT, Launcher, Program, Started
from kernel_services.manager.units.base import (
    NOT_RUNNING,
    READY_TIMEOUT_NANOSECONDS,
    STOP_TIMEOUT_NANOSECONDS,
    Unit,
)

BLOCK_PROGRAM = "kernel_services.block.main"
FILE_PROGRAM = "kernel_services.filesystem.main"
BLOCK_PRIORITY = 1
BLOCK_HEAP_BYTES = 0x40000
MOUNTS = ((b"kernel-boot", b"boot"), (b"kernel-data", b"data"))
ROLE_SEPARATOR = b","
ROOT = b""
NO_CAPABILITY = 0
VIEW_RIGHTS = {FILES_READ: NAMESPACE_READ, FILES_READ_WRITE: NAMESPACE_READ | NAMESPACE_WRITE}
NOT_READY = "the file service is not running"


class StorageUnit(Unit):
    def __init__(self, launcher: Launcher, block_devices: list[int]) -> None:
        super().__init__(STORAGE)
        self._launcher = launcher
        self._devices = block_devices
        self._blocks: list[Started] = []
        self._service: Started | None = None
        self._root = NO_CAPABILITY
        self._views: dict[str, tuple[int, int]] = {}
        self.namespace: files.Namespace | None = None

    def start(self, policy: ServicePolicy) -> bool:
        try:
            self._start_blocks()
            self._start_service(policy)
        except KernelError:
            self._stop_parts()
            return False
        return True

    def stop(self) -> bool:
        return self._stop_parts()

    def is_alive(self) -> bool:
        service = self._service
        if service is None or processes.has_exited(service.process):
            return False
        return all(not processes.has_exited(block.process) for block in self._blocks)

    def collect(self) -> str:
        description = NOT_RUNNING
        service = self._service
        if service is not None and processes.has_exited(service.process):
            self._service = None
            self._forget_namespace()
            reason, value = processes.collect(service)
            description = "part=files " + processes.describe(reason, value)
        for block in list(self._blocks):
            if processes.has_exited(block.process):
                self._blocks.remove(block)
                reason, value = processes.collect(block)
                description = "part=block " + processes.describe(reason, value)
        self._stop_parts()
        return description

    def endpoint(self) -> int:
        if self._service is None:
            return NO_ENDPOINT
        return self._service.endpoint

    def evict(self, client: int) -> None:
        if self._service is None:
            return
        try:
            services.call(self._service.endpoint, OPERATION_EVICT, encode_size(client))
        except KernelError:
            return

    def view(self, mode: str) -> int:
        namespace = self.namespace
        if namespace is None or mode not in VIEW_RIGHTS:
            raise KernelError(BAD_STATE, NOT_READY)
        if mode not in self._views:
            self._views[mode] = namespace.subspace(ROOT, VIEW_RIGHTS[mode])
        return self._views[mode][1]

    def _start_blocks(self) -> None:
        program = Program(BLOCK_PROGRAM, BLOCK_PRIORITY, BLOCK_HEAP_BYTES, True)
        argument = encode_supervisor(self._launcher.identity)
        for device in self._devices:
            grants = ((device, DRIVER_RIGHTS),)
            self._blocks.append(
                self._launcher.launch(program, grants, argument, READY_TIMEOUT_NANOSECONDS)
            )

    def _start_service(self, policy: ServicePolicy) -> None:
        names = []
        grants = []
        for identity, mount in MOUNTS:
            for block in self._blocks:
                if block.announcement == identity:
                    names.append(mount)
                    grants.append((block.endpoint, RIGHT_SEND))
        program = Program(FILE_PROGRAM, policy.priority, policy.heap_bytes, True)
        argument = encode_supervisor(self._launcher.identity, ROLE_SEPARATOR.join(names))
        service = self._launcher.launch(program, tuple(grants), argument, READY_TIMEOUT_NANOSECONDS)
        self._service = service
        _payload, self._root = services.call(service.endpoint, OPERATION_ROOT)
        self.namespace = files.Namespace(service.endpoint, self._root)

    def _forget_namespace(self) -> None:
        for mode in sorted(self._views):
            capabilities.close(self._views[mode][1])
        self._views = {}
        if self._root != NO_CAPABILITY:
            capabilities.close(self._root)
            self._root = NO_CAPABILITY
        self.namespace = None

    def _stop_parts(self) -> bool:
        clean = True
        service = self._service
        self._service = None
        self._forget_namespace()
        if service is not None:
            identity = service.identity
            clean = processes.stop(service, True, STOP_TIMEOUT_NANOSECONDS)
            for block in self._blocks:
                self._evict_from(block, identity)
        for block in self._blocks:
            clean = processes.stop(block, True, STOP_TIMEOUT_NANOSECONDS) and clean
        self._blocks = []
        return clean

    def _evict_from(self, block: Started, client: int) -> None:
        try:
            services.call(block.endpoint, BLOCK_EVICT, encode_client(client))
        except KernelError:
            return
