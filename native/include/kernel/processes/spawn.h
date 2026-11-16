#ifndef KERNEL_PROCESSES_SPAWN_H
#define KERNEL_PROCESSES_SPAWN_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/processes/process.h"
#include "kernel/processes/spawn_request.h"

struct spawn_quota {
    uint64_t memory_frames;
    uint32_t capabilities;
    uint64_t ipc_pending_bytes;
};

int64_t spawn_submit(const struct process *requester, const struct spawn_request *request);
const struct spawn_request *spawn_pending(uint64_t *requester);
int64_t spawn_admit(struct spawn_quota quota);
void spawn_reject(int64_t error);
void spawn_cancel(const struct process *requester);
int64_t spawn_initial(const char *name, uint32_t name_length, uint64_t heap_bytes,
                      struct spawn_quota quota);
uint64_t spawn_footprint_frames(uint64_t heap_bytes);

#endif
