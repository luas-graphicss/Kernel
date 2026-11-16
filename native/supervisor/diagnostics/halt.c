#include "kernel/diagnostics/halt.h"

#include "kernel/arch/sbi.h"
#include "kernel/diagnostics/console.h"

_Noreturn void kernel_halt(bool succeeded)
{
    console_text("kernel:");
    console_field_text("status", succeeded ? "ok" : "failed");
    console_end_line();
    sbi_shutdown();
}

_Noreturn void kernel_panic(const char *reason)
{
    console_text("panic:");
    console_field_text("reason", reason);
    console_end_line();
    kernel_halt(false);
}
