#ifndef KERNEL_DEVICES_UART_NS16550_H
#define KERNEL_DEVICES_UART_NS16550_H

#include <stdbool.h>
#include <stdint.h>

#define UART_NS16550_REGISTER_BYTES 8u

struct uart_ns16550 {
    volatile uint8_t *registers;
};

bool uart_ns16550_write_byte(const struct uart_ns16550 *uart, uint8_t byte);
bool uart_ns16550_try_write_byte(const struct uart_ns16550 *uart, uint8_t byte);
bool uart_ns16550_read_byte(const struct uart_ns16550 *uart, uint8_t *byte);
void uart_ns16550_enable_receive_interrupt(const struct uart_ns16550 *uart);

#endif
