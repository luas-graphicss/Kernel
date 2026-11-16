#ifndef KERNEL_ARCH_CPU_H
#define KERNEL_ARCH_CPU_H

#include <stdbool.h>
#include <stdint.h>

void mmu_activate(uint64_t root);
uint64_t cpu_time_read(void);
void cpu_timer_interrupt_enable(void);
bool cpu_timer_is_pending(void);
void cpu_wait_for_interrupt(void);

#endif
