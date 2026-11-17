#ifndef KERNEL_PORT_PLATFORM_H
#define KERNEL_PORT_PLATFORM_H

#include <stddef.h>

struct runtime_memory {
    void *heap_start;
    void *heap_end;
    void *stack_top;
    size_t stack_bytes;
};

struct runtime_memory platform_runtime_memory(void);
void platform_console_write(const char *bytes, size_t length);
void platform_collection_begins(void);
void platform_collection_ends(void);
_Noreturn void platform_fatal(const char *reason);

#endif
