#ifndef KERNEL_ARCH_USER_CONTEXT_H
#define KERNEL_ARCH_USER_CONTEXT_H

#define KERNEL_CONTEXT_FRAME 0
#define KERNEL_CONTEXT_SCRATCH 8
#define KERNEL_CONTEXT_RETURN_ADDRESS 16
#define KERNEL_CONTEXT_SAVED 24
#define KERNEL_CONTEXT_BYTES 128

#ifdef __ASSEMBLER__

    .macro kernel_saved_registers operation
    .irp index, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
    \operation s\index, (KERNEL_CONTEXT_SAVED + \index * 8)(sp)
    .endr
    .endm

#else

#include <stdint.h>

#include "kernel/arch/trap_frame.h"

uint64_t user_initial_status(void);
void user_context_enter(struct trap_frame *frame);

#endif

#endif
