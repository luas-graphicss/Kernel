#include "kernel/timers/timer.h"

#include "kernel/arch/cpu.h"
#include "kernel/arch/interrupts.h"
#include "kernel/arch/sbi.h"
#include "kernel/diagnostics/console.h"
#include "kernel/diagnostics/halt.h"
#include "kernel/timers/clock.h"

static uint64_t frequency;

void timer_init(uint64_t ticks_per_second)
{
    if (!clock_frequency_is_supported(ticks_per_second)) {
        kernel_panic("unsupported-timebase");
    }
    frequency = ticks_per_second;
    timer_disarm();
    cpu_timer_interrupt_enable();
    console_text("boot:");
    console_field_decimal("timebase-hz", frequency);
    console_end_line();
}

uint64_t timer_frequency(void)
{
    return frequency;
}

uint64_t timer_now(void)
{
    return cpu_time_read();
}

uint64_t timer_now_nanoseconds(void)
{
    return clock_ticks_to_nanoseconds(cpu_time_read(), frequency);
}

uint64_t timer_ticks_from_nanoseconds(uint64_t nanoseconds)
{
    return clock_nanoseconds_to_ticks(nanoseconds, frequency);
}

void timer_arm(uint64_t deadline)
{
    sbi_timer_set(deadline);
}

void timer_disarm(void)
{
    sbi_timer_set(CLOCK_NEVER);
}

bool timer_is_pending(void)
{
    return cpu_timer_is_pending();
}

void timer_wait_until(uint64_t deadline)
{
    timer_arm(deadline);
    while (!cpu_timer_is_pending() && !cpu_external_interrupt_is_pending() &&
           cpu_time_read() < deadline) {
        cpu_wait_for_interrupt();
    }
    timer_disarm();
}
