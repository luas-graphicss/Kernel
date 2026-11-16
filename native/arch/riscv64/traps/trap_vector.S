#include "kernel/arch/status.h"
#include "kernel/arch/trap_frame.h"
#include "kernel/arch/user_context.h"

    .macro save_registers
    .irp index, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31
    sd x\index, (\index * 8)(sp)
    .endr
    .endm

    .macro save_trap_state base
    csrr t0, sepc
    sd t0, TRAP_FRAME_PROGRAM_COUNTER(\base)
    csrr t0, sstatus
    sd t0, TRAP_FRAME_STATUS(\base)
    csrr t0, scause
    sd t0, TRAP_FRAME_CAUSE(\base)
    csrr t0, stval
    sd t0, TRAP_FRAME_VALUE(\base)
    .endm

    .section .text.trap_vector, "ax", @progbits
    .globl trap_vector
    .type trap_vector, @function
    .balign 4
trap_vector:
    csrrw sp, sscratch, sp
    bnez sp, trap_with_user_context
    csrrw sp, sscratch, sp
supervisor_trap:
    csrw sscratch, t0
    la t0, emergency_stack_top
    addi t0, t0, -TRAP_FRAME_BYTES
    sd sp, (REGISTER_STACK_POINTER * 8)(t0)
    mv sp, t0
    csrrw t0, sscratch, zero
    save_registers
    save_trap_state sp
    mv a0, sp
    tail supervisor_trap_fatal
trap_with_user_context:
    sd t6, KERNEL_CONTEXT_SCRATCH(sp)
    csrr t6, sstatus
    andi t6, t6, SSTATUS_SPP
    beqz t6, user_trap
    ld t6, KERNEL_CONTEXT_SCRATCH(sp)
    csrrw sp, sscratch, zero
    j supervisor_trap
user_trap:
    ld t6, KERNEL_CONTEXT_FRAME(sp)
    .irp index, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30
    sd x\index, (\index * 8)(t6)
    .endr
    ld t0, KERNEL_CONTEXT_SCRATCH(sp)
    sd t0, (31 * 8)(t6)
    csrrw t0, sscratch, zero
    sd t0, (REGISTER_STACK_POINTER * 8)(t6)
    save_trap_state t6
    .option push
    .option arch, +d
    float_registers fsd, t6
    frcsr t0
    sd t0, USER_CONTEXT_FLOAT_CONTROL(t6)
    .option pop
    li t0, SSTATUS_FS
    csrc sstatus, t0
    ld ra, KERNEL_CONTEXT_RETURN_ADDRESS(sp)
    kernel_saved_registers ld
    addi sp, sp, KERNEL_CONTEXT_BYTES
    ret
    .size trap_vector, . - trap_vector
