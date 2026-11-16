#ifndef KERNEL_DEVICES_INTERRUPTS_H
#define KERNEL_DEVICES_INTERRUPTS_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/devices/device_inventory.h"

typedef void (*interrupt_handler)(void *context);

void interrupts_attach(const struct interrupt_controller_description *controller);
bool interrupts_bind(uint32_t source, interrupt_handler handler, void *context);
void interrupts_dispatch(void);
uint64_t interrupts_handled(void);

#endif
