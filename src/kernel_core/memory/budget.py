from kernel_protocol.errors.codes import INVALID_ARGUMENT, LIMIT_EXCEEDED, KernelError

PROFILE_FIELDS = 7


class ResourceProfile:
    def __init__(self, values: tuple[int, ...]) -> None:
        if len(values) != PROFILE_FIELDS:
            raise KernelError(INVALID_ARGUMENT, "resource profile has the wrong number of limits")
        for value in values:
            if value < 1:
                raise KernelError(INVALID_ARGUMENT, "every limit of the profile must be positive")
        (
            self.memory_bytes,
            self.processes,
            self.supervisor_heap_bytes,
            self.process_heap_bytes,
            self.capabilities_per_process,
            self.ipc_pending_bytes_per_process,
            self.ipc_pending_bytes_global,
        ) = values


def check_profile(profile: ResourceProfile, machine_bytes: int, user_region_bytes: int) -> None:
    if machine_bytes < profile.memory_bytes:
        raise KernelError(LIMIT_EXCEEDED, "the machine has less memory than the profile requires")
    if profile.supervisor_heap_bytes + user_region_bytes > profile.memory_bytes:
        raise KernelError(LIMIT_EXCEEDED, "reserved regions exceed the memory of the profile")
    if profile.process_heap_bytes > user_region_bytes:
        raise KernelError(INVALID_ARGUMENT, "the heap of a process cannot exceed the user region")
    if profile.ipc_pending_bytes_per_process > profile.ipc_pending_bytes_global:
        raise KernelError(INVALID_ARGUMENT, "the ipc budget of a process exceeds the global budget")
