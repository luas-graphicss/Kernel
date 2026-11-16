#ifndef KERNEL_DEVICES_INTERRUPT_CONTROLLER_H
#define KERNEL_DEVICES_INTERRUPT_CONTROLLER_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/devices/device_inventory.h"
#include "kernel/memory/range.h"

#define INTERRUPT_CONTROLLER_PAGES 3u

bool interrupt_controller_pages(const struct interrupt_controller_description *description,
                                struct memory_range pages[INTERRUPT_CONTROLLER_PAGES]);
void interrupt_controller_attach(const struct interrupt_controller_description *description);
void interrupt_controller_enable(uint32_t source);
void interrupt_controller_disable(uint32_t source);
uint32_t interrupt_controller_claim(void);
void interrupt_controller_complete(uint32_t source);

#endif
