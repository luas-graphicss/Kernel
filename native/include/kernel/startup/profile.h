#ifndef KERNEL_STARTUP_PROFILE_H
#define KERNEL_STARTUP_PROFILE_H

#include <stdint.h>

struct resource_profile {
    uint64_t memory_bytes;
    uint64_t processes;
    uint64_t process_heap_bytes;
    uint64_t capabilities_per_process;
    uint64_t ipc_pending_bytes_per_process;
    uint64_t ipc_pending_bytes_global;
};

const struct resource_profile *resource_profile_compiled(void);

#endif
