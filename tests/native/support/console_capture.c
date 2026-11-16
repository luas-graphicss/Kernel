#include "console_capture.h"

#include <string.h>

#include "kernel/diagnostics/console.h"

static char captured[CONSOLE_CAPTURE_BYTES];
static size_t captured_length;

void console_capture_reset(void)
{
    captured_length = 0;
}

size_t console_capture_length(void)
{
    return captured_length;
}

const char *console_capture_bytes(void)
{
    return captured;
}

void console_write(const char *bytes, size_t length)
{
    size_t available = CONSOLE_CAPTURE_BYTES - captured_length;
    size_t copied = length < available ? length : available;

    memcpy(captured + captured_length, bytes, copied);
    captured_length += copied;
}
