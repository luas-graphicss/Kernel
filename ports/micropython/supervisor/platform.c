#include "platform.h"

#include <stdint.h>

#include "kernel/diagnostics/console.h"
#include "kernel/diagnostics/halt.h"
#include "kernel/memory/image.h"

struct runtime_memory platform_runtime_memory(void)
{
    return (struct runtime_memory){
        .heap_start = (void *)(uintptr_t)supervisor_heap_start,
        .heap_end = (void *)(uintptr_t)supervisor_heap_end,
        .stack_top = (void *)(uintptr_t)supervisor_stack_top,
        .stack_bytes = (size_t)(supervisor_stack_top - supervisor_stack_bottom),
    };
}

void platform_console_write(const char *bytes, size_t length)
{
    console_write(bytes, length);
}

_Noreturn void platform_fatal(const char *reason)
{
    kernel_panic(reason);
}
