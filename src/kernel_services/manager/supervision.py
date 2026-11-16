from kernel_protocol.configuration.graph import dependents_of
from kernel_protocol.configuration.model import ServicePolicy
from kernel_protocol.services.control import (
    SERVICE_BLOCKED,
    SERVICE_DEGRADED,
    SERVICE_READY,
    SERVICE_STARTING,
    SERVICE_STOPPED,
    SYSTEM_DEGRADED,
    SYSTEM_RUNNING,
    ServiceStatus,
)
from kernel_services.manager.journal import report
from kernel_services.manager.units.base import Unit

NANOSECONDS_PER_SECOND = 1000000000
MAX_COUNTED = 255


class Supervised:
    def __init__(self, unit: Unit, policy: ServicePolicy) -> None:
        self.unit = unit
        self.policy = policy
        self.state = SERVICE_STOPPED
        self.failures: list[int] = []
        self.starts = 0


class Supervisor:
    def __init__(self) -> None:
        self._entries: dict[str, Supervised] = {}
        self._order: tuple[str, ...] = ()
        self._needs: dict[str, tuple[str, ...]] = {}

    def add(self, unit: Unit, policy: ServicePolicy) -> None:
        entry = self._entries.get(unit.name)
        if entry is None:
            self._entries[unit.name] = Supervised(unit, policy)
        else:
            entry.policy = policy
        self._needs[unit.name] = policy.needs

    def arrange(self, order: tuple[str, ...]) -> None:
        self._order = order

    def adopt(self, name: str) -> None:
        entry = self._entries[name]
        entry.state = SERVICE_READY
        entry.starts += 1

    def is_ready(self, name: str) -> bool:
        entry = self._entries.get(name)
        return entry is not None and entry.state == SERVICE_READY

    def start_all(self, now: int) -> bool:
        for name in self._order:
            entry = self._entries[name]
            if entry.state == SERVICE_STOPPED or entry.state == SERVICE_BLOCKED:
                self._bring_up(entry, now)
        return self.state() == SYSTEM_RUNNING

    def check(self, now: int) -> None:
        for name in self._order:
            entry = self._entries[name]
            if entry.state == SERVICE_READY and not entry.unit.is_alive():
                self._recover(entry, now)

    def stop_all(self) -> bool:
        clean = True
        for index in range(len(self._order)):
            entry = self._entries[self._order[len(self._order) - 1 - index]]
            if entry.state == SERVICE_READY:
                clean = self._stop(entry) and clean
        return clean

    def state(self) -> int:
        for name in self._order:
            if self._entries[name].state != SERVICE_READY:
                return SYSTEM_DEGRADED
        return SYSTEM_RUNNING

    def statuses(self) -> list[ServiceStatus]:
        statuses = []
        for name in self._order:
            entry = self._entries[name]
            statuses.append(
                ServiceStatus(
                    name,
                    entry.state,
                    len(entry.failures),
                    entry.policy.restarts,
                    entry.starts if entry.starts < MAX_COUNTED else MAX_COUNTED,
                )
            )
        return statuses

    def _bring_up(self, entry: Supervised, now: int) -> bool:
        name = entry.unit.name
        for need in entry.policy.needs:
            if not self.is_ready(need):
                if entry.state != SERVICE_BLOCKED:
                    entry.state = SERVICE_BLOCKED
                    report(f"service={name} state=blocked waiting-for={need}")
                return False
        while True:
            entry.state = SERVICE_STARTING
            if entry.unit.start(entry.policy):
                entry.state = SERVICE_READY
                entry.starts += 1
                report(f"service={name} state=ready")
                return True
            report(f"service={name} state=failed stage=start")
            if not self._may_restart(entry, now):
                return False

    def _recover(self, entry: Supervised, now: int) -> None:
        name = entry.unit.name
        report(f"service={name} state=failed {entry.unit.collect()}")
        dependents = self._ready_dependents(name)
        for index in range(len(dependents)):
            self._stop(dependents[len(dependents) - 1 - index])
        if self._may_restart(entry, now):
            self._bring_up(entry, now)
        for dependent in dependents:
            self._bring_up(dependent, now)

    def _may_restart(self, entry: Supervised, now: int) -> bool:
        policy = entry.policy
        entry.failures = [
            failure for failure in entry.failures if now - failure < policy.window_nanoseconds
        ]
        if len(entry.failures) >= policy.restarts:
            entry.state = SERVICE_DEGRADED
            window = policy.window_nanoseconds // NANOSECONDS_PER_SECOND
            report(
                f"service={entry.unit.name} state=degraded "
                f"restarts={len(entry.failures)} window-seconds={window}"
            )
            return False
        entry.failures.append(now)
        report(
            f"service={entry.unit.name} state=restarting "
            f"attempt={len(entry.failures)} limit={policy.restarts}"
        )
        return True

    def _ready_dependents(self, name: str) -> list[Supervised]:
        names = dependents_of(name, self._needs)
        return [
            self._entries[candidate]
            for candidate in self._order
            if candidate in names and self._entries[candidate].state == SERVICE_READY
        ]

    def _stop(self, entry: Supervised) -> bool:
        clean = entry.unit.stop()
        entry.state = SERVICE_STOPPED
        report(f"service={entry.unit.name} state=stopped clean={1 if clean else 0}")
        return clean
