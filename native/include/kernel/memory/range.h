#ifndef KERNEL_MEMORY_RANGE_H
#define KERNEL_MEMORY_RANGE_H

#include <stdbool.h>
#include <stdint.h>

struct memory_range {
    uint64_t base;
    uint64_t length;
};

bool memory_range_end(struct memory_range range, uint64_t *end);
bool memory_range_contains(struct memory_range outer, struct memory_range inner);
bool memory_ranges_overlap(struct memory_range first, struct memory_range second);

#endif
