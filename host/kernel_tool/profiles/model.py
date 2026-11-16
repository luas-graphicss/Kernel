from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Machine:
    emulator: str
    machine: str
    cpu: str
    harts: int
    memory_mib: int
    accelerator: str
    globals: tuple[str, ...]
    firmware: str


@dataclass(frozen=True, slots=True)
class Layout:
    kernel_base: int
    user_region_base: int
    user_region_bytes: int
    supervisor_stack_bytes: int
    emergency_stack_bytes: int
    user_heap_bytes: int
    user_stack_bytes: int


@dataclass(frozen=True, slots=True)
class Limits:
    memory_bytes: int
    processes: int
    supervisor_heap_bytes: int
    process_heap_bytes: int
    capabilities_per_process: int
    delegation_depth: int
    ipc_inline_payload_bytes: int
    endpoint_messages: int
    ipc_pending_bytes_per_process: int
    ipc_pending_bytes_global: int


@dataclass(frozen=True, slots=True)
class Deadlines:
    boot_seconds: int
    selftest_seconds: int
    soak_seconds: int


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    machine: Machine
    layout: Layout
    limits: Limits
    deadlines: Deadlines
