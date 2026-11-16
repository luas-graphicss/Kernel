#ifndef KERNEL_DIAGNOSTICS_COUNTERS_H
#define KERNEL_DIAGNOSTICS_COUNTERS_H

#include <stdint.h>

#include "kernel/abi/process.h"

struct activity_counters {
    uint64_t user_faults;
    uint64_t context_switches;
    uint64_t preemptions;
    uint64_t timer_interrupts;
};

struct activity_counters *activity_counters(void);
void resource_counters_read(uint64_t counters[COUNTERS]);

#endif
