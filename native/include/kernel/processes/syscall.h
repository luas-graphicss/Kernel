#ifndef KERNEL_PROCESSES_SYSCALL_H
#define KERNEL_PROCESSES_SYSCALL_H

#include <stdint.h>

#include "kernel/memory/range.h"

#define SYSCALL_ARGUMENTS 6u

enum syscall_outcome {
    SYSCALL_RESUME,
    SYSCALL_EXIT,
};

struct syscall_request {
    uint64_t number;
    uint64_t arguments[SYSCALL_ARGUMENTS];
};

struct syscall_result {
    enum syscall_outcome outcome;
    int64_t value;
};

struct syscall_result syscall_dispatch(const struct syscall_request *request,
                                       struct memory_range region);

#endif
