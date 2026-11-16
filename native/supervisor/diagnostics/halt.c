#include "kernel/diagnostics/halt.h"

#include "kernel/abi/power.h"
#include "kernel/arch/sbi.h"
#include "kernel/diagnostics/console.h"

static uint32_t requested_action = POWER_ACTION_SHUTDOWN;

void kernel_power_request(uint32_t action)
{
    requested_action = action;
}

_Noreturn void kernel_halt(bool succeeded)
{
    bool restarts = succeeded && requested_action == POWER_ACTION_RESTART;

    if (restarts) {
        console_text("kernel:");
        console_field_text("power", "restart");
        console_end_line();
    }
    console_text("kernel:");
    console_field_text("status", succeeded ? "ok" : "failed");
    console_end_line();
    if (restarts) {
        sbi_restart();
    }
    sbi_shutdown();
}

_Noreturn void kernel_panic(const char *reason)
{
    console_text("panic:");
    console_field_text("reason", reason);
    console_end_line();
    kernel_halt(false);
}
