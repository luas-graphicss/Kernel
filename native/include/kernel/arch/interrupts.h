#ifndef KERNEL_ARCH_INTERRUPTS_H
#define KERNEL_ARCH_INTERRUPTS_H

#define INTERRUPT_SUPERVISOR_EXTERNAL (1 << 9)
#define TRAP_CAUSE_SUPERVISOR_EXTERNAL 9

#ifndef __ASSEMBLER__

#include <stdbool.h>

void cpu_external_interrupts_enable(void);
bool cpu_external_interrupt_is_pending(void);

#endif

#endif
