from kernel_protocol.configuration.errors import DEPENDENCY_CYCLE, ConfigurationError


def start_order(needs: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    ordered: list[str] = []
    remaining = sorted(needs)
    while remaining:
        ready = [
            name
            for name in remaining
            if len([need for need in needs[name] if need not in ordered]) == 0
        ]
        if not ready:
            raise ConfigurationError(DEPENDENCY_CYCLE, remaining[0])
        for name in ready:
            ordered.append(name)
            remaining.remove(name)
    return tuple(ordered)


def dependents_of(name: str, needs: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    found: list[str] = []
    pending = [name]
    while pending:
        current = pending.pop()
        for candidate in sorted(needs):
            if current in needs[candidate] and candidate not in found:
                found.append(candidate)
                pending.append(candidate)
    return tuple(found)
