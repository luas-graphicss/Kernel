#ifndef KERNEL_PROCESSES_RUN_H
#define KERNEL_PROCESSES_RUN_H

#include <stdbool.h>
#include <stdint.h>

#define RUN_STALE 0u
#define RUN_PREEMPTED 1u
#define RUN_YIELDED 2u
#define RUN_BLOCKED 3u
#define RUN_EXITED 4u
#define RUN_SPAWN 5u

struct run_outcome {
    uint32_t result;
    uint64_t value;
    uint64_t detail;
};

struct run_outcome supervisor_run(uint64_t handle, uint64_t quantum_nanoseconds);
bool supervisor_idle(void);

#endif
