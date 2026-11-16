#ifndef KERNEL_DIAGNOSTICS_HALT_H
#define KERNEL_DIAGNOSTICS_HALT_H

#include <stdbool.h>
#include <stdint.h>

void kernel_power_request(uint32_t action);
_Noreturn void kernel_halt(bool succeeded);
_Noreturn void kernel_panic(const char *reason);

#endif
