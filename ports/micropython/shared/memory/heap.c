#include "memory/heap.h"

#include "py/gc.h"

void *runtime_heap_allocate(size_t bytes)
{
    return gc_alloc(bytes, 0);
}

size_t runtime_heap_block_bytes(const void *block)
{
    return gc_nbytes(block);
}

void runtime_heap_collect(void)
{
    gc_collect();
}

struct runtime_heap_usage runtime_heap_usage(void)
{
    gc_info_t info;

    gc_info(&info);
    return (struct runtime_heap_usage){
        .total_bytes = info.total,
        .used_bytes = info.used,
        .free_bytes = info.free,
    };
}
