#include "kernel/memory/physical_memory.h"

#include <stddef.h>

#include "kernel/diagnostics/console.h"
#include "kernel/diagnostics/halt.h"

#define MANAGED_FRAMES (PROFILE_MEMORY_BYTES / FRAME_BYTES)

static struct frame_record records[MANAGED_FRAMES];
static struct frame_pool pool;

static const struct memory_region *next_region(const struct memory_layout *layout, uint64_t cursor)
{
    const struct memory_region *next = NULL;

    for (size_t index = 0; index < layout->region_count; index++) {
        const struct memory_region *region = &layout->regions[index];

        if (region->range.base >= cursor && (next == NULL || region->range.base < next->range.base)) {
            next = region;
        }
    }
    return next;
}

static void add_usable(uint64_t base, uint64_t end)
{
    if (end > base &&
        frame_pool_add_usable(&pool, (struct memory_range){base, end - base}) != FRAME_OK) {
        kernel_panic("physical-memory-layout");
    }
}

void physical_memory_init(const struct boot_environment *environment)
{
    const struct memory_layout *layout = &environment->layout;
    uint64_t managed_bytes = layout->ram.length < PROFILE_MEMORY_BYTES ? layout->ram.length
                                                                       : PROFILE_MEMORY_BYTES;
    uint64_t end = layout->ram.base + managed_bytes;
    uint64_t cursor = layout->ram.base;

    if (!frame_pool_init(&pool, layout->ram.base, records, (uint32_t)(managed_bytes / FRAME_BYTES))) {
        kernel_panic("physical-memory-base");
    }
    while (cursor < end) {
        const struct memory_region *region = next_region(layout, cursor);
        uint64_t limit = region != NULL && region->range.base < end ? region->range.base : end;

        add_usable(cursor, limit);
        if (region == NULL || region->range.base >= end) {
            break;
        }
        cursor = region->range.base + region->range.length;
    }
    if (pool.free_frames <= SUPERVISOR_RESERVE_FRAMES) {
        kernel_panic("physical-memory-exhausted");
    }
    pool.reserve_frames = SUPERVISOR_RESERVE_FRAMES;
    console_text("boot:");
    console_field_decimal("frames", pool.usable_frames);
    console_field_decimal("reserved-frames", pool.reserve_frames);
    console_end_line();
}

struct frame_pool *physical_memory_pool(void)
{
    return &pool;
}
