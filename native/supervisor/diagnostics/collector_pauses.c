#include "kernel/diagnostics/collector_pauses.h"

#include "kernel/timers/clock.h"
#include "kernel/timers/timer.h"

static struct pause_histogram pauses;
static uint64_t began_at;

void collector_pause_begins(void)
{
    began_at = timer_now();
}

void collector_pause_ends(void)
{
    uint64_t ticks = timer_now() - began_at;

    pause_histogram_record(&pauses, clock_ticks_to_nanoseconds(ticks, timer_frequency()));
}

struct pause_summary collector_pauses_summary(void)
{
    return pause_histogram_summary(&pauses);
}
