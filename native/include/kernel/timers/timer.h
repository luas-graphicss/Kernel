#ifndef KERNEL_TIMERS_TIMER_H
#define KERNEL_TIMERS_TIMER_H

#include <stdbool.h>
#include <stdint.h>

void timer_init(uint64_t frequency);
uint64_t timer_frequency(void);
uint64_t timer_now(void);
uint64_t timer_now_nanoseconds(void);
uint64_t timer_ticks_from_nanoseconds(uint64_t nanoseconds);
void timer_arm(uint64_t deadline);
void timer_disarm(void);
bool timer_is_pending(void);
void timer_wait_until(uint64_t deadline);

#endif
