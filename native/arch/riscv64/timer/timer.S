#include "kernel/arch/status.h"

    .section .text.cpu_time_read, "ax", @progbits
    .globl cpu_time_read
    .type cpu_time_read, @function
cpu_time_read:
    rdtime a0
    ret
    .size cpu_time_read, . - cpu_time_read

    .section .text.cpu_timer_interrupt_enable, "ax", @progbits
    .globl cpu_timer_interrupt_enable
    .type cpu_timer_interrupt_enable, @function
cpu_timer_interrupt_enable:
    li t0, INTERRUPT_SUPERVISOR_TIMER
    csrs sie, t0
    ret
    .size cpu_timer_interrupt_enable, . - cpu_timer_interrupt_enable

    .section .text.cpu_timer_is_pending, "ax", @progbits
    .globl cpu_timer_is_pending
    .type cpu_timer_is_pending, @function
cpu_timer_is_pending:
    csrr a0, sip
    andi a0, a0, INTERRUPT_SUPERVISOR_TIMER
    snez a0, a0
    ret
    .size cpu_timer_is_pending, . - cpu_timer_is_pending

    .section .text.cpu_wait_for_interrupt, "ax", @progbits
    .globl cpu_wait_for_interrupt
    .type cpu_wait_for_interrupt, @function
cpu_wait_for_interrupt:
    wfi
    ret
    .size cpu_wait_for_interrupt, . - cpu_wait_for_interrupt
