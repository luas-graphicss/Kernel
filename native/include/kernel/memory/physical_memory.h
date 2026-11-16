#ifndef KERNEL_MEMORY_PHYSICAL_MEMORY_H
#define KERNEL_MEMORY_PHYSICAL_MEMORY_H

#include "kernel/memory/frame_pool.h"
#include "kernel/startup/environment.h"

#define SUPERVISOR_RESERVE_FRAMES 512u

void physical_memory_init(const struct boot_environment *environment);
struct frame_pool *physical_memory_pool(void);

#endif
