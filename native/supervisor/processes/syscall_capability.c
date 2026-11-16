#include "kernel/processes/syscall.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/ipc/endpoint.h"
#include "kernel/objects/kernel_objects.h"

#define ENDPOINT_RIGHTS (RIGHT_SEND | RIGHT_RECEIVE | RIGHT_DELEGATE)
#define RIGHTS_WIDTH_MASK 0xffffffffull

struct syscall_result syscall_capability_close(struct process *caller, const uint64_t *arguments)
{
    return syscall_resume(capability_close(kernel_capabilities(), caller->index, arguments[0]));
}

struct syscall_result syscall_capability_derive(struct process *caller, const uint64_t *arguments)
{
    if ((arguments[1] & ~RIGHTS_WIDTH_MASK) != 0) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    return syscall_resume(
        capability_delegate(caller->index, arguments[0], (uint32_t)arguments[1], caller->index));
}

struct syscall_result syscall_capability_revoke(struct process *caller, const uint64_t *arguments)
{
    return syscall_resume(capability_revoke(kernel_capabilities(), caller->index, arguments[0]));
}

struct syscall_result syscall_capability_inspect(struct process *caller, const uint64_t *arguments)
{
    struct capability capability;
    const struct kernel_object *object;

    if (!capability_find(kernel_capabilities(), caller->index, arguments[0], &capability)) {
        return syscall_resume(-KERNEL_ERROR_INVALID_HANDLE);
    }
    object = object_find(kernel_object_table(), capability.object);
    if (object == NULL) {
        return syscall_resume(-KERNEL_ERROR_INVALID_HANDLE);
    }
    return syscall_resume((int64_t)(object->kind | (capability.rights << INSPECT_RIGHTS_SHIFT) |
                                    ((uint32_t)capability.depth << INSPECT_DEPTH_SHIFT)));
}

struct syscall_result syscall_endpoint_create(struct process *caller, const uint64_t *arguments)
{
    int64_t endpoint = endpoint_allocate(caller->index);
    uint64_t object;
    int64_t handle;

    (void)arguments;
    if (endpoint < 0) {
        return syscall_resume(endpoint);
    }
    object = object_create(kernel_object_table(), OBJECT_ENDPOINT, caller->index,
                           (uint64_t)endpoint);
    if (object == SLOT_INVALID_HANDLE) {
        endpoint_dispose((uint32_t)endpoint);
        return syscall_resume(-KERNEL_ERROR_LIMIT_EXCEEDED);
    }
    handle = capability_install(kernel_capabilities(), caller->index, object, ENDPOINT_RIGHTS);
    if (handle < 0) {
        object_release(kernel_object_table(), object);
    }
    return syscall_resume(handle);
}
