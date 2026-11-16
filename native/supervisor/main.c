#include "kernel/diagnostics/halt.h"
#include "kernel/memory/kernel_space.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/objects/kernel_objects.h"
#include "kernel/startup/environment.h"
#include "kernel/startup/policy.h"
#include "kernel/timers/timer.h"

_Noreturn void supervisor_main(uint64_t hart, const void *device_tree_blob)
{
    const struct boot_environment *environment = boot_environment_load(hart, device_tree_blob);

    physical_memory_init(environment);
    kernel_space_init(environment);
    timer_init(environment->description.timebase_frequency);
    kernel_objects_init();
    kernel_halt(supervisor_policy_run());
}
