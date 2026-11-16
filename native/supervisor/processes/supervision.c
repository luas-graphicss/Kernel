#include "kernel/processes/supervision.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/process.h"
#include "kernel/objects/kernel_objects.h"
#include "kernel/processes/process.h"

int64_t supervision_kill(uint64_t handle)
{
    struct process *process = process_find(handle);

    if (process == NULL) {
        return -KERNEL_ERROR_INVALID_HANDLE;
    }
    if (process->state == PROCESS_DYING) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    process_terminate(process, WAIT_REASON_KILLED, 0);
    return KERNEL_OK;
}

int64_t supervision_release(uint64_t handle)
{
    const struct process *process = process_find(handle);

    if (process == NULL) {
        return -KERNEL_ERROR_INVALID_HANDLE;
    }
    if (process->state != PROCESS_DYING) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    object_release(kernel_object_table(), process->object);
    return KERNEL_OK;
}

uint32_t supervision_state(uint64_t handle)
{
    const struct process *process = process_find(handle);

    return process == NULL ? (uint32_t)PROCESS_FREE : (uint32_t)process->state;
}
