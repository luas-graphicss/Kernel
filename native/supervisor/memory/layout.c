#include "kernel/memory/layout.h"

enum memory_layout_status memory_layout_begin(struct memory_layout *layout, struct memory_range ram,
                                              uint64_t required_bytes)
{
    uint64_t ram_end;

    *layout = (struct memory_layout){.ram = ram};
    if (!memory_range_end(ram, &ram_end)) {
        return MEMORY_LAYOUT_ADDRESS_OVERFLOW;
    }
    if (ram.length < required_bytes) {
        return MEMORY_LAYOUT_INSUFFICIENT_RAM;
    }
    return MEMORY_LAYOUT_OK;
}

enum memory_layout_status memory_layout_reserve(struct memory_layout *layout, const char *name,
                                                struct memory_range range)
{
    uint64_t range_end;

    layout->conflict = NULL;
    if (range.length == 0) {
        return MEMORY_LAYOUT_EMPTY_REGION;
    }
    if (!memory_range_end(range, &range_end)) {
        return MEMORY_LAYOUT_ADDRESS_OVERFLOW;
    }
    if (!memory_range_contains(layout->ram, range)) {
        return MEMORY_LAYOUT_OUTSIDE_RAM;
    }
    for (size_t index = 0; index < layout->region_count; index++) {
        if (memory_ranges_overlap(layout->regions[index].range, range)) {
            layout->conflict = layout->regions[index].name;
            return MEMORY_LAYOUT_OVERLAP;
        }
    }
    if (layout->region_count == MEMORY_LAYOUT_MAX_REGIONS) {
        return MEMORY_LAYOUT_TOO_MANY_REGIONS;
    }
    layout->regions[layout->region_count] = (struct memory_region){.name = name, .range = range};
    layout->region_count++;
    return MEMORY_LAYOUT_OK;
}

const char *memory_layout_status_name(enum memory_layout_status status)
{
    switch (status) {
    case MEMORY_LAYOUT_OK:
        return "ok";
    case MEMORY_LAYOUT_INSUFFICIENT_RAM:
        return "insufficient-ram";
    case MEMORY_LAYOUT_EMPTY_REGION:
        return "empty-region";
    case MEMORY_LAYOUT_ADDRESS_OVERFLOW:
        return "address-overflow";
    case MEMORY_LAYOUT_OUTSIDE_RAM:
        return "outside-ram";
    case MEMORY_LAYOUT_OVERLAP:
        return "overlap";
    case MEMORY_LAYOUT_TOO_MANY_REGIONS:
        return "too-many-regions";
    }
    return "unknown";
}
