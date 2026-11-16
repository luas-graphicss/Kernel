#include "kernel/arch/status.h"

    .section .text.entry, "ax", @progbits
    .globl _start
    .type _start, @function
_start:
    csrw sie, zero
    csrw sscratch, zero
    li t0, SSTATUS_SIE | SSTATUS_FS
    csrc sstatus, t0
    la t0, trap_vector
    csrw stvec, t0
    la sp, supervisor_stack_top
    la t0, kernel_bss_start
    la t1, kernel_bss_end
clear_bss:
    bgeu t0, t1, enter_supervisor
    sd zero, 0(t0)
    addi t0, t0, 8
    j clear_bss
enter_supervisor:
    tail supervisor_main
    .size _start, . - _start
