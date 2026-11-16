#include "kernel/arch/status.h"

    .section .text.mmu_activate, "ax", @progbits
    .globl mmu_activate
    .type mmu_activate, @function
mmu_activate:
    srli a0, a0, SATP_FRAME_SHIFT
    li t0, SATP_MODE_SV39
    slli t0, t0, SATP_MODE_SHIFT
    or a0, a0, t0
    csrw satp, a0
    sfence.vma
    ret
    .size mmu_activate, . - mmu_activate
