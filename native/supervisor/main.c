#include "kernel/diagnostics/halt.h"
#include "kernel/startup/environment.h"

_Noreturn void supervisor_main(uint64_t hart, const void *device_tree_blob)
{
    boot_environment_load(hart, device_tree_blob);
    kernel_halt(true);
}
