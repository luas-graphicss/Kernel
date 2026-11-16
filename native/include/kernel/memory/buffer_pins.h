#ifndef KERNEL_MEMORY_BUFFER_PINS_H
#define KERNEL_MEMORY_BUFFER_PINS_H

#include <stdbool.h>
#include <stdint.h>

bool buffer_pin(uint32_t buffer, uint64_t offset, uint64_t length, uint64_t *physical);
void buffer_unpin(uint32_t buffer);
uint64_t buffer_pinned_count(void);

#endif
