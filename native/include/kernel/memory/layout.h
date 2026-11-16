#ifndef KERNEL_MEMORY_LAYOUT_H
#define KERNEL_MEMORY_LAYOUT_H

#include <stddef.h>
#include <stdint.h>

#include "kernel/memory/range.h"

#define MEMORY_LAYOUT_MAX_REGIONS 32u

enum memory_layout_status {
    MEMORY_LAYOUT_OK,
    MEMORY_LAYOUT_INSUFFICIENT_RAM,
    MEMORY_LAYOUT_EMPTY_REGION,
    MEMORY_LAYOUT_ADDRESS_OVERFLOW,
    MEMORY_LAYOUT_OUTSIDE_RAM,
    MEMORY_LAYOUT_OVERLAP,
    MEMORY_LAYOUT_TOO_MANY_REGIONS,
};

struct memory_region {
    const char *name;
    struct memory_range range;
};

struct memory_layout {
    struct memory_range ram;
    struct memory_region regions[MEMORY_LAYOUT_MAX_REGIONS];
    size_t region_count;
    const char *conflict;
};

enum memory_layout_status memory_layout_begin(struct memory_layout *layout, struct memory_range ram,
                                              uint64_t required_bytes);
enum memory_layout_status memory_layout_reserve(struct memory_layout *layout, const char *name,
                                                struct memory_range range);
const char *memory_layout_status_name(enum memory_layout_status status);

#endif
