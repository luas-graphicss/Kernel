    .section .text.trap_probe_illegal_instruction, "ax", @progbits
    .globl trap_probe_illegal_instruction
    .type trap_probe_illegal_instruction, @function
trap_probe_illegal_instruction:
    unimp
    ret
    .size trap_probe_illegal_instruction, . - trap_probe_illegal_instruction
