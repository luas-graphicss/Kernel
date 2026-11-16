#ifndef KERNEL_DIAGNOSTICS_CONSOLE_H
#define KERNEL_DIAGNOSTICS_CONSOLE_H

#include <stddef.h>
#include <stdint.h>

void console_attach_uart(uint64_t registers_base);
void console_write(const char *bytes, size_t length);
void console_text(const char *text);
void console_field_text(const char *name, const char *value);
void console_field_hex(const char *name, uint64_t value);
void console_field_decimal(const char *name, uint64_t value);
void console_end_line(void);

#endif
