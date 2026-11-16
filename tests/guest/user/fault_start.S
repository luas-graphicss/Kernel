    .section .text.start, "ax", @progbits
    .globl _start
    .type _start, @function
_start:
    unimp
    .size _start, . - _start
