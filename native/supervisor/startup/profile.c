#include "kernel/startup/profile.h"

static const struct resource_profile compiled = {
    .memory_bytes = PROFILE_MEMORY_BYTES,
    .processes = PROFILE_PROCESSES,
    .process_heap_bytes = PROFILE_PROCESS_HEAP_BYTES,
    .capabilities_per_process = PROFILE_CAPABILITIES_PER_PROCESS,
    .ipc_pending_bytes_per_process = PROFILE_IPC_PENDING_BYTES_PER_PROCESS,
    .ipc_pending_bytes_global = PROFILE_IPC_PENDING_BYTES_GLOBAL,
};

const struct resource_profile *resource_profile_compiled(void)
{
    return &compiled;
}
