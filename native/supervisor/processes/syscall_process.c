#include "kernel/processes/syscall.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/process.h"
#include "kernel/abi/rights.h"
#include "kernel/diagnostics/counters.h"
#include "kernel/memory/endian.h"
#include "kernel/objects/kernel_objects.h"
#include "kernel/processes/spawn.h"
#include "kernel/processes/spawn_request.h"

#define DOUBLE_WORD_BYTES 8u

static int64_t target_process(const struct process *caller, uint64_t handle, uint32_t rights,
                              struct process **target)
{
    struct capability capability;
    struct kernel_object *object;
    int64_t status =
        capability_require(caller->index, handle, OBJECT_PROCESS, rights, &capability, &object);

    if (status != KERNEL_OK) {
        return status;
    }
    *target = process_find(object->payload);
    return *target == NULL ? -KERNEL_ERROR_INVALID_HANDLE : KERNEL_OK;
}

struct syscall_result syscall_process_spawn(struct process *caller, const uint64_t *arguments)
{
    uint8_t bytes[SPAWN_REQUEST_BYTES];
    struct capability capability;
    struct kernel_object *object;
    struct spawn_request request;
    int64_t status = capability_require(caller->index, arguments[0], OBJECT_SYSTEM, RIGHT_ADMIN,
                                        &capability, &object);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (!user_memory_read(&caller->space, arguments[1], bytes, SPAWN_REQUEST_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    status = spawn_request_parse(bytes, &request);
    if (status == KERNEL_OK) {
        status = spawn_submit(caller, &request);
    }
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    return (struct syscall_result){.action = SYSCALL_SPAWN};
}

struct syscall_result syscall_process_wait(struct process *caller, const uint64_t *arguments)
{
    struct process *target;
    uint64_t deadline;
    int64_t status = target_process(caller, arguments[0], RIGHT_READ, &target);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (target->state == PROCESS_DYING) {
        return syscall_resume((int64_t)(((uint64_t)target->exit_reason << WAIT_REASON_SHIFT) |
                                        (target->exit_value & WAIT_VALUE_MASK)));
    }
    status = wait_chain_check(caller, target->index);
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (!syscall_deadline(arguments[1], &deadline)) {
        return syscall_resume(-KERNEL_ERROR_TIMED_OUT);
    }
    wait_begin(caller, WAIT_PROCESS, true, target->handle, deadline, target->index);
    return syscall_block();
}

struct syscall_result syscall_process_kill(struct process *caller, const uint64_t *arguments)
{
    struct process *target;
    int64_t status = target_process(caller, arguments[0], RIGHT_ADMIN, &target);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (target->state == PROCESS_DYING) {
        return syscall_resume(-KERNEL_ERROR_BAD_STATE);
    }
    process_terminate(target, WAIT_REASON_KILLED, 0);
    if (target == caller) {
        return (struct syscall_result){.action = SYSCALL_EXIT};
    }
    process_event_push(EVENT_EXITED, target->handle);
    return syscall_resume(KERNEL_OK);
}

struct syscall_result syscall_process_interrupt(struct process *caller, const uint64_t *arguments)
{
    struct process *target;
    int64_t status = target_process(caller, arguments[0], RIGHT_ADMIN, &target);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (target->state != PROCESS_BLOCKED) {
        return syscall_resume(-KERNEL_ERROR_BAD_STATE);
    }
    wait_finish(target, -KERNEL_ERROR_CANCELLED);
    return syscall_resume(KERNEL_OK);
}

struct syscall_result syscall_system_counters(struct process *caller, const uint64_t *arguments)
{
    uint8_t bytes[COUNTERS_BYTES];
    uint64_t counters[COUNTERS];
    struct capability capability;
    struct kernel_object *object;
    int64_t status = capability_require(caller->index, arguments[0], OBJECT_SYSTEM, RIGHT_READ,
                                        &capability, &object);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (arguments[2] < COUNTERS_BYTES) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    resource_counters_read(counters);
    for (uint32_t index = 0; index < COUNTERS; index++) {
        little_endian_write(bytes + index * DOUBLE_WORD_BYTES, DOUBLE_WORD_BYTES, counters[index]);
    }
    if (!user_memory_write(&caller->space, arguments[1], bytes, COUNTERS_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    return syscall_resume(COUNTERS);
}
