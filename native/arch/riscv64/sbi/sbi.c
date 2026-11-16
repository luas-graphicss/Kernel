#include "kernel/arch/sbi.h"

#include <stdint.h>

#define EXTENSION_DEBUG_CONSOLE 0x4442434eul
#define EXTENSION_SYSTEM_RESET 0x53525354ul
#define FUNCTION_CONSOLE_WRITE 0ul
#define FUNCTION_SYSTEM_RESET 0ul
#define RESET_TYPE_SHUTDOWN 0ul
#define RESET_REASON_NONE 0ul

size_t sbi_console_write(const char *bytes, size_t length)
{
    struct sbi_result result = sbi_call(EXTENSION_DEBUG_CONSOLE, FUNCTION_CONSOLE_WRITE, length,
                                        (unsigned long)(uintptr_t)bytes, 0);
    if (result.error != 0 || result.value < 0) {
        return 0;
    }
    return (size_t)result.value;
}

_Noreturn void sbi_shutdown(void)
{
    sbi_call(EXTENSION_SYSTEM_RESET, FUNCTION_SYSTEM_RESET, RESET_TYPE_SHUTDOWN, RESET_REASON_NONE,
             0);
    cpu_wait_forever();
}
