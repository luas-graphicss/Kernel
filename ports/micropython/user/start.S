    .section .text.start, "ax", @progbits
    .globl _start
    .type _start, @function
_start:
    tail user_main
    .size _start, . - _start
