#include "kernel/arch/trap_frame.h"

    .macro save_registers
    .irp index, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31
    sd x\index, (\index * 8)(sp)
    .endr
    .endm

    .macro save_trap_state
    csrr t0, sepc
    sd t0, TRAP_FRAME_PROGRAM_COUNTER(sp)
    csrr t0, sstatus
    sd t0, TRAP_FRAME_STATUS(sp)
    csrr t0, scause
    sd t0, TRAP_FRAME_CAUSE(sp)
    csrr t0, stval
    sd t0, TRAP_FRAME_VALUE(sp)
    .endm

    .section .text.trap_vector, "ax", @progbits
    .globl trap_vector
    .type trap_vector, @function
    .balign 4
trap_vector:
    csrw sscratch, t0
    la t0, emergency_stack_top
    addi t0, t0, -TRAP_FRAME_BYTES
    sd sp, (REGISTER_STACK_POINTER * 8)(t0)
    mv sp, t0
    csrrw t0, sscratch, zero
    save_registers
    save_trap_state
    mv a0, sp
    tail supervisor_trap_fatal
    .size trap_vector, . - trap_vector
