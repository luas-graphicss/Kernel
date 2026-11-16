#ifndef KERNEL_MEMORY_FRAME_POOL_H
#define KERNEL_MEMORY_FRAME_POOL_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/memory/range.h"

#define FRAME_SHIFT 12u
#define FRAME_BYTES (1ull << FRAME_SHIFT)
#define FRAME_MAX_ORDER 10u
#define FRAME_ORDERS (FRAME_MAX_ORDER + 1u)
#define FRAME_NO_LINK UINT32_MAX
#define FRAME_UNLIMITED_ALLOCATIONS UINT64_MAX

enum frame_status {
    FRAME_OK,
    FRAME_BAD_RANGE,
    FRAME_BAD_ORDER,
    FRAME_OUT_OF_MEMORY,
    FRAME_RESERVE_PROTECTED,
    FRAME_NOT_ALLOCATED,
};

enum frame_purpose {
    FRAME_FOR_SUPERVISOR,
    FRAME_FOR_PROCESS,
};

enum frame_state {
    FRAME_UNUSABLE,
    FRAME_FREE,
    FRAME_ALLOCATED,
    FRAME_INTERIOR,
};

struct frame_record {
    uint32_t next;
    uint32_t previous;
    uint8_t order;
    uint8_t state;
};

struct frame_pool {
    uint64_t base;
    uint32_t frame_count;
    struct frame_record *records;
    uint32_t free_heads[FRAME_ORDERS];
    uint64_t usable_frames;
    uint64_t free_frames;
    uint64_t reserve_frames;
    uint64_t allocations_before_failure;
    uint64_t refused_allocations;
};

bool frame_pool_init(struct frame_pool *pool, uint64_t base, struct frame_record *records,
                     uint32_t frame_count);
enum frame_status frame_pool_add_usable(struct frame_pool *pool, struct memory_range range);
enum frame_status frame_pool_allocate(struct frame_pool *pool, uint32_t order,
                                      enum frame_purpose purpose, uint64_t *address);
enum frame_status frame_pool_free(struct frame_pool *pool, uint64_t address, uint32_t order);
bool frame_order_for_bytes(uint64_t bytes, uint32_t *order);

#endif
