#ifndef KERNEL_ARCH_TRAP_FRAME_H
#define KERNEL_ARCH_TRAP_FRAME_H

#define TRAP_FRAME_REGISTERS 32
#define TRAP_FRAME_PROGRAM_COUNTER 256
#define TRAP_FRAME_STATUS 264
#define TRAP_FRAME_CAUSE 272
#define TRAP_FRAME_VALUE 280
#define TRAP_FRAME_BYTES 288

#define REGISTER_RETURN_ADDRESS 1
#define REGISTER_STACK_POINTER 2

#ifndef __ASSEMBLER__

#include <stddef.h>
#include <stdint.h>

struct trap_frame {
    uint64_t registers[TRAP_FRAME_REGISTERS];
    uint64_t program_counter;
    uint64_t status;
    uint64_t cause;
    uint64_t value;
};

_Static_assert(offsetof(struct trap_frame, program_counter) == TRAP_FRAME_PROGRAM_COUNTER,
               "assembly offset of program_counter");
_Static_assert(offsetof(struct trap_frame, status) == TRAP_FRAME_STATUS,
               "assembly offset of status");
_Static_assert(offsetof(struct trap_frame, cause) == TRAP_FRAME_CAUSE, "assembly offset of cause");
_Static_assert(offsetof(struct trap_frame, value) == TRAP_FRAME_VALUE, "assembly offset of value");
_Static_assert(sizeof(struct trap_frame) == TRAP_FRAME_BYTES, "assembly size of the trap frame");

const char *trap_cause_name(uint64_t cause);
void trap_report(const char *mode, const struct trap_frame *frame);
_Noreturn void supervisor_trap_fatal(const struct trap_frame *frame);

#endif

#endif
