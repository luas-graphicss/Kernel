from kernel_protocol.configuration.model import ServicePolicy
from kernel_protocol.errors.codes import KernelError
from kernel_protocol.services.lifecycle import encode_supervisor
from kernel_services.manager import processes
from kernel_services.manager.processes import NO_ENDPOINT, Launcher, Program, Started

READY_TIMEOUT_NANOSECONDS = 20000000000
STOP_TIMEOUT_NANOSECONDS = 20000000000
NOT_RUNNING = "reason=none value=0"


class Unit:
    def __init__(self, name: str) -> None:
        self.name = name

    def start(self, policy: ServicePolicy) -> bool:
        return False

    def stop(self) -> bool:
        return True

    def is_alive(self) -> bool:
        return False

    def collect(self) -> str:
        return NOT_RUNNING

    def endpoint(self) -> int:
        return NO_ENDPOINT

    def evict(self, client: int) -> None:
        return


class ProcessUnit(Unit):
    def __init__(self, name: str, module: str, is_server: bool, launcher: Launcher) -> None:
        super().__init__(name)
        self._module = module
        self._is_server = is_server
        self._launcher = launcher
        self.ready_timeout_nanoseconds = READY_TIMEOUT_NANOSECONDS
        self.started: Started | None = None

    def grants(self) -> tuple[tuple[int, int], ...]:
        return ()

    def role(self) -> bytes:
        return b""

    def prepare(self, started: Started) -> None:
        return

    def release(self, started: Started) -> None:
        return

    def start(self, policy: ServicePolicy) -> bool:
        program = Program(self._module, policy.priority, policy.heap_bytes, self._is_server)
        argument = encode_supervisor(self._launcher.identity, self.role())
        try:
            started = self._launcher.launch(
                program, self.grants(), argument, self.ready_timeout_nanoseconds
            )
        except KernelError:
            return False
        self.started = started
        try:
            self.prepare(started)
        except KernelError:
            self.stop()
            return False
        return True

    def stop(self) -> bool:
        started = self.started
        if started is None:
            return True
        self.started = None
        self.release(started)
        return processes.stop(started, self._is_server, STOP_TIMEOUT_NANOSECONDS)

    def is_alive(self) -> bool:
        return self.started is not None and not processes.has_exited(self.started.process)

    def collect(self) -> str:
        started = self.started
        if started is None:
            return NOT_RUNNING
        self.started = None
        self.release(started)
        reason, value = processes.collect(started)
        return processes.describe(reason, value)

    def endpoint(self) -> int:
        if self.started is None:
            return NO_ENDPOINT
        return self.started.endpoint

    def identity(self) -> int:
        if self.started is None:
            return 0
        return self.started.identity
