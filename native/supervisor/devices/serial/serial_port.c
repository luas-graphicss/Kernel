#include "kernel/devices/serial_port.h"

#include "kernel/abi/devices.h"
#include "kernel/devices/uart_ns16550.h"

#define BYTES_PER_INTERRUPT 64u

static struct uart_ns16550 uart;
static uint8_t input[SERIAL_INPUT_BYTES];
static uint32_t input_head;
static uint32_t input_count;
static uint64_t dropped;

void serial_port_attach(uint64_t registers)
{
    uart.registers = (volatile uint8_t *)(uintptr_t)registers;
    input_head = 0;
    input_count = 0;
    dropped = 0;
    uart_ns16550_enable_receive_interrupt(&uart);
}

void serial_port_receive(void)
{
    uint8_t byte;

    for (uint32_t received = 0; received < BYTES_PER_INTERRUPT; received++) {
        if (!uart_ns16550_read_byte(&uart, &byte)) {
            return;
        }
        if (input_count == SERIAL_INPUT_BYTES) {
            dropped++;
            continue;
        }
        input[(input_head + input_count) % SERIAL_INPUT_BYTES] = byte;
        input_count++;
    }
}

bool serial_port_has_input(void)
{
    return input_count != 0;
}

uint32_t serial_port_read(uint8_t *bytes, uint32_t capacity)
{
    uint32_t count = input_count < capacity ? input_count : capacity;

    for (uint32_t index = 0; index < count; index++) {
        bytes[index] = input[(input_head + index) % SERIAL_INPUT_BYTES];
    }
    input_head = (input_head + count) % SERIAL_INPUT_BYTES;
    input_count -= count;
    return count;
}

uint32_t serial_port_write(const uint8_t *bytes, uint32_t length)
{
    uint32_t written = 0;

    while (written < length && uart_ns16550_try_write_byte(&uart, bytes[written])) {
        written++;
    }
    return written;
}

uint64_t serial_port_dropped(void)
{
    return dropped;
}
