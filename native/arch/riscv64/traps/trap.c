#include "kernel/arch/trap_frame.h"

#include <stdbool.h>

#include "kernel/arch/sbi.h"
#include "kernel/diagnostics/console.h"
#include "kernel/diagnostics/halt.h"

#define CAUSE_INTERRUPT_FLAG (1ull << 63)

static const char *const exception_names[] = {
    "instruction-address-misaligned",
    "instruction-access-fault",
    "illegal-instruction",
    "breakpoint",
    "load-address-misaligned",
    "load-access-fault",
    "store-address-misaligned",
    "store-access-fault",
    "environment-call-from-user",
    "environment-call-from-supervisor",
    "reserved",
    "reserved",
    "instruction-page-fault",
    "load-page-fault",
    "reserved",
    "store-page-fault",
};

const char *trap_cause_name(uint64_t cause)
{
    if ((cause & CAUSE_INTERRUPT_FLAG) != 0) {
        return "interrupt";
    }
    if (cause >= sizeof(exception_names) / sizeof(exception_names[0])) {
        return "reserved";
    }
    return exception_names[cause];
}

void trap_report(const char *mode, const struct trap_frame *frame)
{
    console_text("trap:");
    console_field_text("mode", mode);
    console_field_text("cause", trap_cause_name(frame->cause));
    console_field_hex("scause", frame->cause);
    console_field_hex("sepc", frame->program_counter);
    console_field_hex("stval", frame->value);
    console_field_hex("sstatus", frame->status);
    console_field_hex("ra", frame->registers[REGISTER_RETURN_ADDRESS]);
    console_field_hex("sp", frame->registers[REGISTER_STACK_POINTER]);
    console_end_line();
}

_Noreturn void supervisor_trap_fatal(const struct trap_frame *frame)
{
    static bool reporting;

    if (reporting) {
        sbi_shutdown();
    }
    reporting = true;
    trap_report("supervisor", frame);
    kernel_panic("unexpected-supervisor-trap");
}
