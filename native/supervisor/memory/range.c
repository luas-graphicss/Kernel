#include "kernel/memory/range.h"

bool memory_range_end(struct memory_range range, uint64_t *end)
{
    if (range.length > UINT64_MAX - range.base) {
        return false;
    }
    *end = range.base + range.length;
    return true;
}

bool memory_range_contains(struct memory_range outer, struct memory_range inner)
{
    uint64_t outer_end;
    uint64_t inner_end;

    if (inner.length == 0 || !memory_range_end(outer, &outer_end) ||
        !memory_range_end(inner, &inner_end)) {
        return false;
    }
    return inner.base >= outer.base && inner_end <= outer_end;
}

bool memory_ranges_overlap(struct memory_range first, struct memory_range second)
{
    uint64_t first_end;
    uint64_t second_end;

    if (!memory_range_end(first, &first_end) || !memory_range_end(second, &second_end)) {
        return true;
    }
    return first.base < second_end && second.base < first_end;
}
