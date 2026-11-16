#include "collector_probes.h"

#define PROBE_BYTES 64
#define SCRUBBED_BYTES 2048
#define FRAME_BYTES 32
#define FRAME_RETURN_ADDRESS 0
#define FRAME_FIRST_SAVED 8
#define FRAME_SECOND_SAVED 16
#define FRAME_ROOT_SLOT 24

    .macro forget_dead_copies
    li t0, SCRUBBED_BYTES
    sub t1, sp, t0
1:
    sd zero, 0(t1)
    addi t1, t1, 8
    bltu t1, sp, 1b
    .irp name, a0, a1, a2, a3, a4, a5, a6, a7, t0, t1, t2, t3, t4, t5, t6
    li \name, 0
    .endr
    .endm

    .macro report_survivors decoy
    call runtime_heap_block_bytes
    li t0, COLLECTOR_PROBE_ROOT_COLLECTED
    beqz a0, 2f
    not a0, \decoy
    call runtime_heap_block_bytes
    li t0, COLLECTOR_PROBE_DECOY_RETAINED
    bnez a0, 2f
    li t0, COLLECTOR_PROBE_PASSED
2:
    mv a0, t0
    .endm

    .macro register_root_probe root, decoy
    .section .text.collector_probe_register_\root, "ax", @progbits
    .globl collector_probe_register_\root
    .type collector_probe_register_\root, @function
collector_probe_register_\root:
    addi sp, sp, -FRAME_BYTES
    sd ra, FRAME_RETURN_ADDRESS(sp)
    sd \root, FRAME_FIRST_SAVED(sp)
    sd \decoy, FRAME_SECOND_SAVED(sp)
    li a0, PROBE_BYTES
    call runtime_heap_allocate
    mv \root, a0
    li a0, PROBE_BYTES
    call runtime_heap_allocate
    not \decoy, a0
    forget_dead_copies
    call runtime_heap_collect
    mv a0, \root
    report_survivors \decoy
    ld ra, FRAME_RETURN_ADDRESS(sp)
    ld \root, FRAME_FIRST_SAVED(sp)
    ld \decoy, FRAME_SECOND_SAVED(sp)
    addi sp, sp, FRAME_BYTES
    ret
    .size collector_probe_register_\root, . - collector_probe_register_\root
    .endm

    register_root_probe s0, s1
    register_root_probe s1, s2
    register_root_probe s2, s3
    register_root_probe s3, s4
    register_root_probe s4, s5
    register_root_probe s5, s6
    register_root_probe s6, s7
    register_root_probe s7, s8
    register_root_probe s8, s9
    register_root_probe s9, s10
    register_root_probe s10, s11
    register_root_probe s11, s0

    .section .text.collector_probe_stack_slot, "ax", @progbits
    .globl collector_probe_stack_slot
    .type collector_probe_stack_slot, @function
collector_probe_stack_slot:
    addi sp, sp, -FRAME_BYTES
    sd ra, FRAME_RETURN_ADDRESS(sp)
    sd s1, FRAME_FIRST_SAVED(sp)
    li a0, PROBE_BYTES
    call runtime_heap_allocate
    sd a0, FRAME_ROOT_SLOT(sp)
    li a0, PROBE_BYTES
    call runtime_heap_allocate
    not s1, a0
    forget_dead_copies
    call runtime_heap_collect
    ld a0, FRAME_ROOT_SLOT(sp)
    report_survivors s1
    sd zero, FRAME_ROOT_SLOT(sp)
    ld ra, FRAME_RETURN_ADDRESS(sp)
    ld s1, FRAME_FIRST_SAVED(sp)
    addi sp, sp, FRAME_BYTES
    ret
    .size collector_probe_stack_slot, . - collector_probe_stack_slot
