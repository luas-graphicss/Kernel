#include "platform.h"

#include <string.h>

#include "kernel/abi/syscalls.h"
#include "process_calls.h"

#define FATAL_EXIT_STATUS 2u
#define FATAL_PREFIX "runtime: fatal reason="

extern char user_heap_start[];
extern char user_heap_end[];
extern char user_stack_bottom[];
extern char user_stack_top[];

struct runtime_memory platform_runtime_memory(void)
{
    return (struct runtime_memory){
        .heap_start = user_heap_start,
        .heap_end = user_heap_end,
        .stack_top = user_stack_top,
        .stack_bytes = (size_t)(user_stack_top - user_stack_bottom),
    };
}

void platform_console_write(const char *bytes, size_t length)
{
    while (length > 0) {
        size_t chunk =
            length < SYSCALL_DEBUG_WRITE_MAX_BYTES ? length : SYSCALL_DEBUG_WRITE_MAX_BYTES;
        long written = process_debug_write(bytes, chunk);

        if (written <= 0) {
            return;
        }
        bytes += written;
        length -= (size_t)written;
    }
}

_Noreturn void platform_fatal(const char *reason)
{
    platform_console_write(FATAL_PREFIX, sizeof(FATAL_PREFIX) - 1u);
    platform_console_write(reason, strlen(reason));
    platform_console_write("\n", 1u);
    process_exit(FATAL_EXIT_STATUS);
}
