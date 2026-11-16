#include "kernel/processes/spawn.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/objects/kernel_objects.h"
#include "kernel/processes/program.h"

#define PROCESS_RIGHTS (RIGHT_READ | RIGHT_ADMIN | RIGHT_DELEGATE)

static struct {
    bool active;
    uint64_t requester;
    struct spawn_request request;
} pending;

static int64_t check_grants(const struct process *requester, const struct spawn_request *request)
{
    for (uint32_t index = 0; index < request->grant_count; index++) {
        uint32_t transferable;
        int64_t status = capability_transferable_rights(
            requester->index, request->grants[index].handle, &transferable);

        if (status != KERNEL_OK) {
            return status;
        }
        if ((request->grants[index].rights & ~transferable) != 0) {
            return -KERNEL_ERROR_ACCESS_DENIED;
        }
    }
    return KERNEL_OK;
}

static int64_t publish(struct process *requester, struct process *child)
{
    int64_t capability;

    object_retain(kernel_object_table(), child->object);
    capability =
        capability_install(kernel_capabilities(), requester->index, child->object, PROCESS_RIGHTS);
    if (capability < 0) {
        object_release(kernel_object_table(), child->object);
        process_terminate(child, WAIT_REASON_KILLED, 0);
        object_release(kernel_object_table(), child->object);
    }
    return capability;
}

int64_t spawn_submit(const struct process *requester, const struct spawn_request *request)
{
    int64_t status = check_grants(requester, request);

    if (status != KERNEL_OK) {
        return status;
    }
    if (request->heap_bytes > PROFILE_PROCESS_HEAP_BYTES) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    pending.active = true;
    pending.requester = requester->handle;
    pending.request = *request;
    return KERNEL_OK;
}

const struct spawn_request *spawn_pending(uint64_t *requester)
{
    if (!pending.active) {
        return NULL;
    }
    *requester = pending.requester;
    return &pending.request;
}

int64_t spawn_admit(struct spawn_quota quota)
{
    struct process *requester = process_find(pending.requester);
    const struct spawn_request *request = &pending.request;
    struct process *child;
    int64_t created;
    int64_t capability;

    if (!pending.active || requester == NULL || requester->state != PROCESS_READY) {
        pending.active = false;
        return -KERNEL_ERROR_BAD_STATE;
    }
    pending.active = false;
    created = process_create(&(struct process_request){
        .name = request->name,
        .name_length = request->name_length,
        .argument = request->argument,
        .argument_length = request->argument_length,
        .heap_bytes = request->heap_bytes,
        .memory_quota_frames = quota.memory_frames,
        .capability_limit = quota.capabilities,
        .ipc_quota_bytes = quota.ipc_pending_bytes,
        .parent = requester->index,
        .grants = request->grants,
        .grant_count = request->grant_count,
    });
    if (created < 0) {
        process_set_result(requester, created);
        return created;
    }
    child = process_find((uint64_t)created);
    capability = publish(requester, child);
    process_set_result(requester, capability);
    return capability < 0 ? capability : created;
}

void spawn_reject(int64_t error)
{
    struct process *requester = process_find(pending.requester);

    if (pending.active && requester != NULL && requester->state == PROCESS_READY) {
        process_set_result(requester, error);
    }
    pending.active = false;
}

void spawn_cancel(const struct process *requester)
{
    if (pending.active && pending.requester == requester->handle) {
        pending.active = false;
    }
}

int64_t spawn_initial(const char *name, uint32_t name_length, uint64_t heap_bytes,
                      struct spawn_quota quota)
{
    if (!program_name_is_valid(name, name_length)) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    return process_create(&(struct process_request){
        .name = name,
        .name_length = name_length,
        .heap_bytes = heap_bytes,
        .memory_quota_frames = quota.memory_frames,
        .capability_limit = quota.capabilities,
        .ipc_quota_bytes = quota.ipc_pending_bytes,
        .parent = PROCESS_NONE,
        .grants_system = true,
    });
}

uint64_t spawn_footprint_frames(uint64_t heap_bytes)
{
    const struct user_image *image = program_image();
    struct user_layout layout;

    if (image == NULL) {
        return 0;
    }
    if (heap_bytes == 0) {
        heap_bytes = image->heap_bytes;
    }
    if (!user_layout_compute(image, program_region(), heap_bytes, &layout)) {
        return 0;
    }
    return layout.private_frames + layout.table_frames;
}
