#ifndef KERNEL_TIMERS_CLOCK_H
#define KERNEL_TIMERS_CLOCK_H

#include <stdbool.h>
#include <stdint.h>

#define CLOCK_NEVER UINT64_MAX
#define CLOCK_NANOSECONDS_PER_SECOND 1000000000ull
#define CLOCK_MAX_FREQUENCY 10000000000ull

bool clock_frequency_is_supported(uint64_t frequency);
uint64_t clock_ticks_to_nanoseconds(uint64_t ticks, uint64_t frequency);
uint64_t clock_nanoseconds_to_ticks(uint64_t nanoseconds, uint64_t frequency);
uint64_t clock_add(uint64_t ticks, uint64_t delta);

#endif
