#ifndef TESTS_NATIVE_SUPPORT_CONSOLE_CAPTURE_H
#define TESTS_NATIVE_SUPPORT_CONSOLE_CAPTURE_H

#include <stddef.h>

#define CONSOLE_CAPTURE_BYTES 1024u

void console_capture_reset(void);
size_t console_capture_length(void);
const char *console_capture_bytes(void);

#endif
