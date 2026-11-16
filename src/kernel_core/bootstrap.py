import _supervisor
from kernel_core.memory.budget import ResourceProfile, check_profile
from kernel_core.processes.admission import ImageRequest, ProcessRegistry
from kernel_protocol.errors.codes import KernelError, error_name

INIT_NAME = "init"
INIT_PRIORITY = 1
IMAGE_ACCEPTED = "ok"
EXIT_REQUESTED = "exit"
EXIT_SUCCEEDED = 0


def report(text: str) -> None:
    print("policy: " + text)


def open_registry() -> ProcessRegistry:
    profile = ResourceProfile(_supervisor.limits())
    _hart, _memory_base, machine_bytes = _supervisor.machine()
    _region_base, region_bytes = _supervisor.user_region()
    check_profile(profile, machine_bytes, region_bytes)
    report(
        f"profile=ok memory-bytes={profile.memory_bytes} processes={profile.processes} "
        f"supervisor-heap-bytes={profile.supervisor_heap_bytes} user-region-bytes={region_bytes}"
    )
    return ProcessRegistry(profile, region_bytes)


def run_init(registry: ProcessRegistry) -> bool:
    status, file_bytes, memory_bytes, heap_bytes, stack_bytes = _supervisor.inspect_boot_module()
    if status != IMAGE_ACCEPTED:
        report(f"rejected=boot-module reason={status}")
        return False
    request = ImageRequest(file_bytes, memory_bytes, heap_bytes, stack_bytes)
    handle = registry.admit(request, INIT_PRIORITY)
    report(
        f"admitted={INIT_NAME} handle={handle} memory-bytes={memory_bytes} "
        f"heap-bytes={heap_bytes} stack-bytes={stack_bytes}"
    )
    if registry.scheduler.select() != handle:
        report(f"rejected={INIT_NAME} reason=not-selected")
        return False
    reason, value = _supervisor.run_boot_module()
    registry.reap(handle)
    report(
        f"reaped={INIT_NAME} reason={reason} value={value} "
        f"live={registry.live()} memory-in-use={registry.memory_in_use()}"
    )
    return reason == EXIT_REQUESTED and value == EXIT_SUCCEEDED


def main() -> bool:
    try:
        return run_init(open_registry())
    except KernelError as error:
        report(f'rejected=request code={error_name(error.code)} detail="{error.detail}"')
        return False
