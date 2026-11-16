#ifndef KERNEL_PROCESSES_SPAWN_REQUEST_H
#define KERNEL_PROCESSES_SPAWN_REQUEST_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/abi/process.h"

struct spawn_grant {
    uint64_t handle;
    uint32_t rights;
};

struct spawn_request {
    uint32_t priority;
    uint64_t heap_bytes;
    uint64_t memory_bytes;
    uint32_t name_length;
    uint32_t argument_length;
    uint32_t grant_count;
    struct spawn_grant grants[PROCESS_GRANTS];
    char name[PROCESS_NAME_BYTES + 1u];
    uint8_t argument[PROCESS_ARGUMENT_BYTES];
};

bool program_name_is_valid(const char *name, uint32_t length);
int64_t spawn_request_parse(const uint8_t *bytes, struct spawn_request *request);

#endif
