#include "kernel/arch/status.h"
#include "kernel/arch/trap_frame.h"
#include "kernel/arch/user_context.h"

    .section .text.user_context_status, "ax", @progbits
    .globl user_context_status
    .type user_context_status, @function
user_context_status:
    csrr a0, sstatus
    li t0, SSTATUS_SPP | SSTATUS_SPIE | SSTATUS_SIE | SSTATUS_SUM | SSTATUS_MXR | SSTATUS_FS
    not t0, t0
    and a0, a0, t0
    li t0, SSTATUS_FS_CLEAN
    or a0, a0, t0
    ret
    .size user_context_status, . - user_context_status

    .section .text.user_context_enter, "ax", @progbits
    .globl user_context_enter
    .type user_context_enter, @function
user_context_enter:
    addi sp, sp, -KERNEL_CONTEXT_BYTES
    sd a0, KERNEL_CONTEXT_FRAME(sp)
    sd ra, KERNEL_CONTEXT_RETURN_ADDRESS(sp)
    kernel_saved_registers sd
    ld t0, TRAP_FRAME_PROGRAM_COUNTER(a0)
    csrw sepc, t0
    ld t0, TRAP_FRAME_STATUS(a0)
    csrw sstatus, t0
    .option push
    .option arch, +d
    float_registers fld, a0
    ld t1, USER_CONTEXT_FLOAT_CONTROL(a0)
    fscsr t1
    .option pop
    csrw sstatus, t0
    mv t6, a0
    csrw sscratch, sp
    .irp index, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30
    ld x\index, (\index * 8)(t6)
    .endr
    ld t6, (31 * 8)(t6)
    sret
    .size user_context_enter, . - user_context_enter
