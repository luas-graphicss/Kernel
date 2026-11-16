#ifndef KERNEL_PORT_USER_STARTUP_H
#define KERNEL_PORT_USER_STARTUP_H

#include <stddef.h>
#include <stdint.h>

#include "kernel/abi/process.h"

struct process_startup {
    char *heap_start;
    char *heap_end;
    char *stack_bottom;
    char *stack_top;
    uint64_t identity;
    size_t handle_count;
    uint64_t handles[PROCESS_GRANTS];
    size_t name_length;
    char name[PROCESS_NAME_BYTES + 1];
    size_t argument_length;
    uint8_t argument[PROCESS_ARGUMENT_BYTES];
};

void process_startup_load(const uint8_t *block);
const struct process_startup *process_startup(void);

#endif
