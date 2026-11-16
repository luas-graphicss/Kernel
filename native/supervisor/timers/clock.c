#include "kernel/timers/clock.h"

static uint64_t scale(uint64_t value, uint64_t from, uint64_t to, bool round_up)
{
    uint64_t whole = value / from;
    uint64_t fraction = (value % from) * to;

    if (round_up) {
        fraction += from - 1u;
    }
    fraction /= from;
    if (whole > UINT64_MAX / to) {
        return UINT64_MAX;
    }
    return clock_add(whole * to, fraction);
}

bool clock_frequency_is_supported(uint64_t frequency)
{
    return frequency != 0 && frequency <= CLOCK_MAX_FREQUENCY;
}

uint64_t clock_ticks_to_nanoseconds(uint64_t ticks, uint64_t frequency)
{
    return scale(ticks, frequency, CLOCK_NANOSECONDS_PER_SECOND, false);
}

uint64_t clock_nanoseconds_to_ticks(uint64_t nanoseconds, uint64_t frequency)
{
    return scale(nanoseconds, CLOCK_NANOSECONDS_PER_SECOND, frequency, true);
}

uint64_t clock_add(uint64_t ticks, uint64_t delta)
{
    return delta > UINT64_MAX - ticks ? UINT64_MAX : ticks + delta;
}
