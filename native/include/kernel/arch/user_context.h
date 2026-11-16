#ifndef KERNEL_ARCH_USER_CONTEXT_H
#define KERNEL_ARCH_USER_CONTEXT_H

#include "kernel/arch/trap_frame.h"

#define KERNEL_CONTEXT_FRAME 0
#define KERNEL_CONTEXT_SCRATCH 8
#define KERNEL_CONTEXT_RETURN_ADDRESS 16
#define KERNEL_CONTEXT_SAVED 24
#define KERNEL_CONTEXT_BYTES 128

#define USER_CONTEXT_FLOAT_REGISTERS 32
#define USER_CONTEXT_FLOATS TRAP_FRAME_BYTES
#define USER_CONTEXT_FLOAT_CONTROL (USER_CONTEXT_FLOATS + USER_CONTEXT_FLOAT_REGISTERS * 8)
#define USER_CONTEXT_BYTES (USER_CONTEXT_FLOAT_CONTROL + 8)

#ifdef __ASSEMBLER__

    .macro kernel_saved_registers operation
    .irp index, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
    \operation s\index, (KERNEL_CONTEXT_SAVED + \index * 8)(sp)
    .endr
    .endm

    .macro float_registers operation, base
    .irp index, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31
    \operation f\index, (USER_CONTEXT_FLOATS + \index * 8)(\base)
    .endr
    .endm

#else

#include <stddef.h>
#include <stdint.h>

struct user_context {
    struct trap_frame frame;
    uint64_t float_registers[USER_CONTEXT_FLOAT_REGISTERS];
    uint64_t float_control;
};

_Static_assert(offsetof(struct user_context, float_registers) == USER_CONTEXT_FLOATS,
               "assembly offset of the float registers");
_Static_assert(offsetof(struct user_context, float_control) == USER_CONTEXT_FLOAT_CONTROL,
               "assembly offset of the float control register");
_Static_assert(sizeof(struct user_context) == USER_CONTEXT_BYTES,
               "assembly size of the user context");

uint64_t user_context_status(void);
void user_context_enter(struct user_context *context);

#endif

#endif
