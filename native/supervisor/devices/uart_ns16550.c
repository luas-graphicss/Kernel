#include "kernel/devices/uart_ns16550.h"

#define RECEIVE_BUFFER 0u
#define TRANSMIT_HOLDING 0u
#define INTERRUPT_ENABLE 1u
#define MODEM_CONTROL 4u
#define LINE_STATUS 5u
#define INTERRUPT_ENABLE_RECEIVED_DATA 0x01u
#define MODEM_CONTROL_INTERRUPT_OUTPUT 0x08u
#define LINE_STATUS_DATA_READY 0x01u
#define LINE_STATUS_TRANSMIT_EMPTY 0x20u
#define TRANSMIT_SPIN_LIMIT 1000000u

bool uart_ns16550_write_byte(const struct uart_ns16550 *uart, uint8_t byte)
{
    for (uint32_t spin = 0; spin < TRANSMIT_SPIN_LIMIT; spin++) {
        if (uart_ns16550_try_write_byte(uart, byte)) {
            return true;
        }
    }
    return false;
}

bool uart_ns16550_try_write_byte(const struct uart_ns16550 *uart, uint8_t byte)
{
    if ((uart->registers[LINE_STATUS] & LINE_STATUS_TRANSMIT_EMPTY) == 0) {
        return false;
    }
    uart->registers[TRANSMIT_HOLDING] = byte;
    return true;
}

bool uart_ns16550_read_byte(const struct uart_ns16550 *uart, uint8_t *byte)
{
    if ((uart->registers[LINE_STATUS] & LINE_STATUS_DATA_READY) == 0) {
        return false;
    }
    *byte = uart->registers[RECEIVE_BUFFER];
    return true;
}

void uart_ns16550_enable_receive_interrupt(const struct uart_ns16550 *uart)
{
    uart->registers[MODEM_CONTROL] = uart->registers[MODEM_CONTROL] | MODEM_CONTROL_INTERRUPT_OUTPUT;
    uart->registers[INTERRUPT_ENABLE] = INTERRUPT_ENABLE_RECEIVED_DATA;
}
