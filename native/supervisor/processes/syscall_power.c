#include "kernel/processes/syscall.h"

#include "kernel/abi/errors.h"
#include "kernel/abi/power.h"
#include "kernel/abi/rights.h"
#include "kernel/diagnostics/halt.h"
#include "kernel/objects/kernel_objects.h"

struct syscall_result syscall_system_power(struct process *caller, const uint64_t *arguments)
{
    struct capability capability;
    struct kernel_object *object;
    int64_t status = capability_require(caller->index, arguments[0], OBJECT_SYSTEM, RIGHT_ADMIN,
                                        &capability, &object);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (arguments[1] != POWER_ACTION_SHUTDOWN && arguments[1] != POWER_ACTION_RESTART) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    kernel_power_request((uint32_t)arguments[1]);
    return syscall_resume(KERNEL_OK);
}
