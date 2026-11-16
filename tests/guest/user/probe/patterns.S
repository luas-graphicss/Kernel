#define SAVED_BYTES 96
#define FLAGS_MASK 0x1f

    .macro saved_registers operation
    .irp index, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
    \operation s\index, (\index * 8)(sp)
    .endr
    .endm

    .macro pattern_registers operation
    .irp name, s0, s1, s2, s3, s4, s5, s6, s7, s8, s9, s10, s11, t3, t4, t5, t6, a2, a3, a4, a5, a6, a7
    \operation \name
    .endr
    .endm

    .macro fill_register name
    mv \name, t2
    add t2, t2, t1
    .endm

    .macro check_register name
    bne \name, t2, registers_differ
    add t2, t2, t1
    .endm

    .macro float_registers operation, failure
    .irp index, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31
    \operation f\index, \failure
    .endr
    .endm

    .macro fill_float name, failure
    fmv.d.x \name, t2
    add t2, t2, t1
    .endm

    .macro check_float name, failure
    fmv.x.d t3, \name
    bne t3, t2, \failure
    add t2, t2, t1
    .endm

    .macro check_clear name, failure
    fmv.x.d t3, \name
    bnez t3, \failure
    .endm

    .section .text.probe_pattern_hold_registers, "ax", @progbits
    .globl probe_pattern_hold_registers
    .type probe_pattern_hold_registers, @function
probe_pattern_hold_registers:
    addi sp, sp, -SAVED_BYTES
    saved_registers sd
    mv t0, a0
    li t1, 0x9e3779b97f4a7c15
    mv t2, t0
    pattern_registers fill_register
registers_round:
    mv t2, t0
    pattern_registers check_register
    addi a1, a1, -1
    bnez a1, registers_round
    li a0, 1
    j registers_done
registers_differ:
    li a0, 0
registers_done:
    saved_registers ld
    addi sp, sp, SAVED_BYTES
    ret
    .size probe_pattern_hold_registers, . - probe_pattern_hold_registers

    .option push
    .option arch, +d

    .section .text.probe_pattern_hold_floats, "ax", @progbits
    .globl probe_pattern_hold_floats
    .type probe_pattern_hold_floats, @function
probe_pattern_hold_floats:
    mv t0, a0
    li t1, 0x9e3779b97f4a7c15
    mv t2, t0
    float_registers fill_float, held_floats_differ
    andi t4, t0, FLAGS_MASK
    fsflags t4
floats_round:
    mv t2, t0
    float_registers check_float, held_floats_differ
    frflags t3
    bne t3, t4, held_floats_differ
    addi a1, a1, -1
    bnez a1, floats_round
    li a0, 1
    ret
held_floats_differ:
    li a0, 0
    ret
    .size probe_pattern_hold_floats, . - probe_pattern_hold_floats

    .section .text.probe_pattern_floats_are_clear, "ax", @progbits
    .globl probe_pattern_floats_are_clear
    .type probe_pattern_floats_are_clear, @function
probe_pattern_floats_are_clear:
    float_registers check_clear, floats_differ
    frcsr t3
    bnez t3, floats_differ
    li a0, 1
    ret
floats_differ:
    li a0, 0
    ret
    .size probe_pattern_floats_are_clear, . - probe_pattern_floats_are_clear

    .option pop

    .section .text.probe_pattern_spin, "ax", @progbits
    .globl probe_pattern_spin
    .type probe_pattern_spin, @function
probe_pattern_spin:
    j probe_pattern_spin
    .size probe_pattern_spin, . - probe_pattern_spin
