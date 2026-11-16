#include "startup.h"

#include <string.h>

#include "kernel/memory/endian.h"

#define DOUBLE_WORD_BYTES 8u

static struct process_startup startup;

static uint64_t field(const uint8_t *block, size_t offset)
{
    return little_endian_read(block + offset, DOUBLE_WORD_BYTES);
}

static size_t bounded(uint64_t value, size_t limit)
{
    return value < limit ? (size_t)value : limit;
}

void process_startup_load(const uint8_t *block)
{
    startup.heap_start = (char *)(uintptr_t)field(block, STARTUP_FIELD_HEAP_START);
    startup.heap_end = (char *)(uintptr_t)field(block, STARTUP_FIELD_HEAP_END);
    startup.stack_bottom = (char *)(uintptr_t)field(block, STARTUP_FIELD_STACK_BOTTOM);
    startup.stack_top = (char *)(uintptr_t)block;
    startup.identity = field(block, STARTUP_FIELD_IDENTITY);
    startup.handle_count = bounded(field(block, STARTUP_FIELD_HANDLE_COUNT), PROCESS_GRANTS);
    for (size_t index = 0; index < startup.handle_count; index++) {
        startup.handles[index] = field(block, STARTUP_FIELD_HANDLES + index * DOUBLE_WORD_BYTES);
    }
    startup.name_length = bounded(field(block, STARTUP_FIELD_NAME_LENGTH), PROCESS_NAME_BYTES);
    memcpy(startup.name, block + STARTUP_FIELD_NAME, startup.name_length);
    startup.name[startup.name_length] = '\0';
    startup.argument_length =
        bounded(field(block, STARTUP_FIELD_ARGUMENT_LENGTH), PROCESS_ARGUMENT_BYTES);
    memcpy(startup.argument, block + STARTUP_FIELD_ARGUMENT, startup.argument_length);
}

const struct process_startup *process_startup(void)
{
    return &startup;
}
