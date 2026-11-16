#ifndef KERNEL_MEMORY_BUFFER_H
#define KERNEL_MEMORY_BUFFER_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/processes/process.h"

#define BUFFER_WINDOW_OFFSET 0x10000000ull
#define BUFFER_WINDOW_STRIDE 0x800000ull

void buffer_table_init(void);
int64_t buffer_allocate(struct process *owner, uint64_t bytes);
void buffer_dispose(uint32_t buffer);
void buffer_destroy_owned(const struct process *owner);
int64_t buffer_map(struct process *process, uint32_t buffer, uint64_t object, bool writable,
                   uint64_t *address, uint64_t *bytes);
int64_t buffer_unmap(struct process *process, uint64_t address);
void buffer_unmap_all(struct process *process);
void buffer_revoke_mappings(struct process *process, uint64_t object);
uint64_t buffer_live_count(void);

#endif
