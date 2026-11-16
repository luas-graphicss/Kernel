#ifndef KERNEL_PORT_MEMORY_HEAP_H
#define KERNEL_PORT_MEMORY_HEAP_H

#include <stddef.h>

struct runtime_heap_usage {
    size_t total_bytes;
    size_t used_bytes;
    size_t free_bytes;
};

void *runtime_heap_allocate(size_t bytes);
size_t runtime_heap_block_bytes(const void *block);
void runtime_heap_collect(void);
struct runtime_heap_usage runtime_heap_usage(void);

#endif
