#ifndef KERNEL_DEVICES_SERIAL_PORT_H
#define KERNEL_DEVICES_SERIAL_PORT_H

#include <stdbool.h>
#include <stdint.h>

void serial_port_attach(uint64_t registers);
void serial_port_receive(void);
bool serial_port_has_input(void);
uint32_t serial_port_read(uint8_t *bytes, uint32_t capacity);
uint32_t serial_port_write(const uint8_t *bytes, uint32_t length);
uint64_t serial_port_dropped(void);

#endif
