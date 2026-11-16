from kernel_client import capabilities
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import KernelError
from kernel_protocol.identity.handles import FIRST_GENERATION, pack_handle

TABLE_SLOTS = 128
GENERATIONS = 8


def table_handles() -> list[int]:
    return [
        pack_handle(index, generation)
        for generation in range(FIRST_GENERATION, FIRST_GENERATION + GENERATIONS)
        for index in range(TABLE_SLOTS)
    ]


def held_capabilities() -> list[tuple[int, int, int]]:
    found: list[tuple[int, int, int]] = []
    known: list[int] = []
    for handle in table_handles() + list(Startup().handles):
        if handle in known:
            continue
        try:
            kind, rights, _depth = capabilities.inspect(handle)
        except KernelError:
            continue
        known.append(handle)
        found.append((handle, kind, rights))
    return found
