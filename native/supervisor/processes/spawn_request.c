#include "kernel/processes/spawn_request.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/memory/endian.h"
#include "kernel/memory/frame_pool.h"

static uint64_t field(const uint8_t *bytes, uint32_t offset, uint32_t width)
{
    return little_endian_read(bytes + offset, width);
}

static bool is_name_character(char character)
{
    return (character >= 'a' && character <= 'z') || (character >= '0' && character <= '9') ||
           character == '_';
}

static bool tail_is_zero(const uint8_t *bytes, uint32_t used, uint32_t capacity)
{
    for (uint32_t index = used; index < capacity; index++) {
        if (bytes[index] != 0) {
            return false;
        }
    }
    return true;
}

static int64_t read_grants(const uint8_t *bytes, struct spawn_request *request)
{
    for (uint32_t index = 0; index < PROCESS_GRANTS; index++) {
        const uint8_t *grant = bytes + SPAWN_FIELD_GRANTS + index * SPAWN_GRANT_BYTES;
        uint64_t handle = field(grant, SPAWN_GRANT_HANDLE, 8);
        uint64_t rights = field(grant, SPAWN_GRANT_RIGHTS, 8);

        if (index >= request->grant_count) {
            if (handle != 0 || rights != 0) {
                return -KERNEL_ERROR_INVALID_ARGUMENT;
            }
            continue;
        }
        if (handle == 0 || rights == 0 || (rights & ~(uint64_t)RIGHTS_ALL) != 0) {
            return -KERNEL_ERROR_INVALID_ARGUMENT;
        }
        request->grants[index] = (struct spawn_grant){.handle = handle, .rights = (uint32_t)rights};
    }
    return KERNEL_OK;
}

bool program_name_is_valid(const char *name, uint32_t length)
{
    bool after_separator = true;

    if (length == 0 || length > PROCESS_NAME_BYTES) {
        return false;
    }
    for (uint32_t index = 0; index < length; index++) {
        if (name[index] == '.') {
            if (after_separator) {
                return false;
            }
            after_separator = true;
        } else if (is_name_character(name[index])) {
            after_separator = false;
        } else {
            return false;
        }
    }
    return !after_separator;
}

int64_t spawn_request_parse(const uint8_t *bytes, struct spawn_request *request)
{
    struct spawn_request parsed = {
        .priority = (uint32_t)field(bytes, SPAWN_FIELD_PRIORITY, 4),
        .heap_bytes = field(bytes, SPAWN_FIELD_HEAP_BYTES, 8),
        .memory_bytes = field(bytes, SPAWN_FIELD_MEMORY_BYTES, 8),
        .name_length = (uint32_t)field(bytes, SPAWN_FIELD_NAME_LENGTH, 4),
        .argument_length = (uint32_t)field(bytes, SPAWN_FIELD_ARGUMENT_LENGTH, 4),
        .grant_count = (uint32_t)field(bytes, SPAWN_FIELD_GRANT_COUNT, 4),
    };
    int64_t status;

    if (field(bytes, SPAWN_FIELD_VERSION, 4) != SPAWN_REQUEST_VERSION) {
        return -KERNEL_ERROR_UNSUPPORTED;
    }
    if (parsed.priority >= PROCESS_PRIORITY_LEVELS || parsed.grant_count > PROCESS_GRANTS ||
        parsed.argument_length > PROCESS_ARGUMENT_BYTES ||
        field(bytes, SPAWN_FIELD_RESERVED, 4) != 0 || parsed.heap_bytes % FRAME_BYTES != 0 ||
        parsed.memory_bytes % FRAME_BYTES != 0) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    if (!program_name_is_valid((const char *)bytes + SPAWN_FIELD_NAME, parsed.name_length) ||
        !tail_is_zero(bytes + SPAWN_FIELD_NAME, parsed.name_length, PROCESS_NAME_BYTES) ||
        !tail_is_zero(bytes + SPAWN_FIELD_ARGUMENT, parsed.argument_length,
                      PROCESS_ARGUMENT_BYTES)) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    status = read_grants(bytes, &parsed);
    if (status != KERNEL_OK) {
        return status;
    }
    for (uint32_t index = 0; index < parsed.name_length; index++) {
        parsed.name[index] = (char)bytes[SPAWN_FIELD_NAME + index];
    }
    for (uint32_t index = 0; index < parsed.argument_length; index++) {
        parsed.argument[index] = bytes[SPAWN_FIELD_ARGUMENT + index];
    }
    *request = parsed;
    return KERNEL_OK;
}
