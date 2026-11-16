    .section .text.sbi_call, "ax", @progbits
    .globl sbi_call
    .type sbi_call, @function
sbi_call:
    mv a7, a0
    mv a6, a1
    mv a0, a2
    mv a1, a3
    mv a2, a4
    ecall
    ret
    .size sbi_call, . - sbi_call

    .section .text.cpu_wait_forever, "ax", @progbits
    .globl cpu_wait_forever
    .type cpu_wait_forever, @function
cpu_wait_forever:
    wfi
    j cpu_wait_forever
    .size cpu_wait_forever, . - cpu_wait_forever
