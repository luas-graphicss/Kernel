#include "kernel/arch/interrupts.h"

    .section .text.cpu_external_interrupts_enable, "ax", @progbits
    .globl cpu_external_interrupts_enable
    .type cpu_external_interrupts_enable, @function
cpu_external_interrupts_enable:
    li t0, INTERRUPT_SUPERVISOR_EXTERNAL
    csrs sie, t0
    ret
    .size cpu_external_interrupts_enable, . - cpu_external_interrupts_enable

    .section .text.cpu_external_interrupt_is_pending, "ax", @progbits
    .globl cpu_external_interrupt_is_pending
    .type cpu_external_interrupt_is_pending, @function
cpu_external_interrupt_is_pending:
    csrr a0, sip
    andi a0, a0, INTERRUPT_SUPERVISOR_EXTERNAL
    snez a0, a0
    ret
    .size cpu_external_interrupt_is_pending, . - cpu_external_interrupt_is_pending
