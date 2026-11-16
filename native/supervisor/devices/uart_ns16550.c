#include "kernel/devices/uart_ns16550.h"

#define TRANSMIT_HOLDING 0u
#define LINE_STATUS 5u
#define LINE_STATUS_TRANSMIT_EMPTY 0x20u
#define TRANSMIT_SPIN_LIMIT 1000000u

bool uart_ns16550_write_byte(const struct uart_ns16550 *uart, uint8_t byte)
{
    for (uint32_t spin = 0; spin < TRANSMIT_SPIN_LIMIT; spin++) {
        if ((uart->registers[LINE_STATUS] & LINE_STATUS_TRANSMIT_EMPTY) != 0) {
            uart->registers[TRANSMIT_HOLDING] = byte;
            return true;
        }
    }
    return false;
}
