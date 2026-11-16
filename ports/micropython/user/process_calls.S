#include "kernel/abi/syscalls.h"

    .section .text.process_debug_write, "ax", @progbits
    .globl process_debug_write
    .type process_debug_write, @function
process_debug_write:
    li a7, SYSCALL_DEBUG_WRITE
    ecall
    ret
    .size process_debug_write, . - process_debug_write

    .section .text.process_exit, "ax", @progbits
    .globl process_exit
    .type process_exit, @function
process_exit:
    li a7, SYSCALL_PROCESS_EXIT
    ecall
exit_did_not_return:
    j exit_did_not_return
    .size process_exit, . - process_exit
