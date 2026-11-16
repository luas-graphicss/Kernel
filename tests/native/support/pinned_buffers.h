#ifndef TESTS_NATIVE_SUPPORT_PINNED_BUFFERS_H
#define TESTS_NATIVE_SUPPORT_PINNED_BUFFERS_H

#include <stdint.h>

#define PINNED_BUFFERS_CAPACITY 8u

void pinned_buffers_reset(void);
uint32_t pinned_buffers_add(uint64_t physical, uint64_t bytes);
uint32_t pinned_buffers_pins(uint32_t buffer);

#endif
