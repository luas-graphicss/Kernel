#include "kernel/diagnostics/console.h"

#include <stdbool.h>

#include "kernel/arch/sbi.h"
#include "kernel/devices/uart_ns16550.h"
#include "kernel/memory/string.h"

#define HEX_DIGITS 16u
#define DECIMAL_DIGITS 20u
#define DECIMAL_BASE 10u
#define NIBBLE_BITS 4u
#define NIBBLE_MASK 0xfu

static struct uart_ns16550 uart;
static bool uart_attached;

static void write_firmware(const char *bytes, size_t length)
{
    while (length > 0) {
        size_t written = sbi_console_write(bytes, length);
        if (written == 0) {
            return;
        }
        bytes += written;
        length -= written;
    }
}

static void write_field_name(const char *name)
{
    console_text(" ");
    console_text(name);
    console_text("=");
}

void console_attach_uart(uint64_t registers_base)
{
    uart.registers = (volatile uint8_t *)(uintptr_t)registers_base;
    uart_attached = true;
}

void console_write(const char *bytes, size_t length)
{
    if (!uart_attached) {
        write_firmware(bytes, length);
        return;
    }
    for (size_t index = 0; index < length; index++) {
        if (!uart_ns16550_write_byte(&uart, (uint8_t)bytes[index])) {
            uart_attached = false;
            write_firmware(bytes + index, length - index);
            return;
        }
    }
}

void console_text(const char *text)
{
    console_write(text, strlen(text));
}

void console_field_text(const char *name, const char *value)
{
    write_field_name(name);
    console_text(value);
}

void console_field_hex(const char *name, uint64_t value)
{
    static const char digits[] = "0123456789abcdef";
    char text[HEX_DIGITS];

    for (size_t index = 0; index < HEX_DIGITS; index++) {
        uint64_t shift = (HEX_DIGITS - 1u - index) * NIBBLE_BITS;
        text[index] = digits[(value >> shift) & NIBBLE_MASK];
    }
    write_field_name(name);
    console_text("0x");
    console_write(text, HEX_DIGITS);
}

void console_field_decimal(const char *name, uint64_t value)
{
    char text[DECIMAL_DIGITS];
    size_t start = DECIMAL_DIGITS;

    do {
        start--;
        text[start] = (char)('0' + value % DECIMAL_BASE);
        value /= DECIMAL_BASE;
    } while (value != 0);
    write_field_name(name);
    console_write(text + start, DECIMAL_DIGITS - start);
}

void console_end_line(void)
{
    console_text("\n");
}
