#include "kernel/processes/syscall.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/process.h"
#include "kernel/abi/rights.h"
#include "kernel/memory/buffer.h"
#include "kernel/memory/endian.h"
#include "kernel/objects/kernel_objects.h"

#define BUFFER_RIGHTS (RIGHT_READ | RIGHT_WRITE | RIGHT_MAP | RIGHT_DELEGATE)
#define MAPPING_RIGHTS (RIGHT_READ | RIGHT_WRITE)
#define DOUBLE_WORD_BYTES 8u

struct syscall_result syscall_buffer_create(struct process *caller, const uint64_t *arguments)
{
    int64_t buffer = buffer_allocate(caller, arguments[0]);
    uint64_t object;
    int64_t handle;

    if (buffer < 0) {
        return syscall_resume(buffer);
    }
    object = object_create(kernel_object_table(), OBJECT_BUFFER, caller->index, (uint64_t)buffer);
    if (object == SLOT_INVALID_HANDLE) {
        buffer_dispose((uint32_t)buffer);
        return syscall_resume(-KERNEL_ERROR_LIMIT_EXCEEDED);
    }
    handle = capability_install(kernel_capabilities(), caller->index, object, BUFFER_RIGHTS);
    if (handle < 0) {
        object_release(kernel_object_table(), object);
    }
    return syscall_resume(handle);
}

struct syscall_result syscall_buffer_map(struct process *caller, const uint64_t *arguments)
{
    uint8_t mapping[BUFFER_MAPPING_BYTES];
    struct capability capability;
    struct kernel_object *object;
    uint64_t rights = arguments[1];
    uint64_t address;
    uint64_t bytes;
    int64_t status;

    if ((rights & ~(uint64_t)MAPPING_RIGHTS) != 0 || (rights & RIGHT_READ) == 0) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    status = capability_require(caller->index, arguments[0], OBJECT_BUFFER,
                                RIGHT_MAP | (uint32_t)rights, &capability, &object);
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (!user_memory_is_writable(&caller->space, arguments[2], BUFFER_MAPPING_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    status = buffer_map(caller, (uint32_t)object->payload, capability.object,
                        (rights & RIGHT_WRITE) != 0, &address, &bytes);
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    little_endian_write(mapping + BUFFER_MAPPING_ADDRESS, DOUBLE_WORD_BYTES, address);
    little_endian_write(mapping + BUFFER_MAPPING_LENGTH, DOUBLE_WORD_BYTES, bytes);
    user_memory_write(&caller->space, arguments[2], mapping, BUFFER_MAPPING_BYTES);
    return syscall_resume(KERNEL_OK);
}

struct syscall_result syscall_buffer_unmap(struct process *caller, const uint64_t *arguments)
{
    return syscall_resume(buffer_unmap(caller, arguments[0]));
}
