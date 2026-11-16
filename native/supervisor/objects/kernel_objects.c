#include "kernel/objects/kernel_objects.h"

#include <stddef.h>

#include "kernel/abi/devices.h"
#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/devices/device_registry.h"
#include "kernel/ipc/call.h"
#include "kernel/ipc/endpoint.h"
#include "kernel/memory/buffer.h"
#include "kernel/processes/process.h"

#define CAPABILITY_SLOTS PROFILE_CAPABILITIES_PER_PROCESS
#define OBJECT_CAPACITY \
    (PROFILE_PROCESSES * CAPABILITY_SLOTS + PROFILE_PROCESSES + DEVICE_SLOTS + 1u)

static struct slot_record object_records[OBJECT_CAPACITY];
static struct kernel_object objects[OBJECT_CAPACITY];
static struct object_table table;
static struct capability_space spaces[PROFILE_PROCESSES];
static struct slot_record capability_records[PROFILE_PROCESSES][CAPABILITY_SLOTS];
static struct capability capabilities[PROFILE_PROCESSES][CAPABILITY_SLOTS];
static struct capability_registry registry;
static uint64_t system_object;

static void dispose_object(void *context, uint64_t handle, struct kernel_object object)
{
    (void)context;
    switch (object.kind) {
    case OBJECT_ENDPOINT:
        endpoint_dispose((uint32_t)object.payload);
        break;
    case OBJECT_BUFFER:
        buffer_dispose((uint32_t)object.payload);
        break;
    case OBJECT_REPLY:
        call_reply_disposed(handle, object);
        break;
    case OBJECT_PROCESS:
        process_reap(object.payload);
        break;
    default:
        break;
    }
}

static void retain_object(void *context, uint64_t handle)
{
    (void)context;
    object_retain(&table, handle);
}

static void release_capability(void *context, uint32_t space, uint64_t handle, uint32_t rights)
{
    const struct kernel_object *object = object_find(&table, handle);

    (void)context;
    if (object != NULL && object->kind == OBJECT_ENDPOINT && (rights & RIGHT_RECEIVE) != 0) {
        endpoint_close((uint32_t)object->payload);
    }
    if (object != NULL && object->kind == OBJECT_BUFFER) {
        buffer_revoke_mappings(process_at(space), handle);
    }
    if (object != NULL && object->kind == OBJECT_DEVICE) {
        device_registry_capability_released(space, handle);
    }
    object_release(&table, handle);
}

void kernel_objects_init(void)
{
    object_table_init(&table, object_records, objects, OBJECT_CAPACITY, dispose_object, NULL);
    capability_registry_init(&registry, spaces, PROFILE_PROCESSES, retain_object,
                             release_capability, NULL);
    for (uint32_t space = 0; space < PROFILE_PROCESSES; space++) {
        capability_space_attach(&registry, space, capability_records[space], capabilities[space],
                                CAPABILITY_SLOTS);
    }
    endpoint_table_init();
    buffer_table_init();
    process_table_init();
    system_object = object_create(&table, OBJECT_SYSTEM, OBJECT_NO_OWNER, 0);
}

struct object_table *kernel_object_table(void)
{
    return &table;
}

struct capability_registry *kernel_capabilities(void)
{
    return &registry;
}

uint64_t kernel_system_object(void)
{
    return system_object;
}

int64_t capability_require(uint32_t space, uint64_t handle, uint32_t kind, uint32_t rights,
                           struct capability *capability, struct kernel_object **object)
{
    struct kernel_object *found;

    if (!capability_find(&registry, space, handle, capability)) {
        return -KERNEL_ERROR_INVALID_HANDLE;
    }
    found = object_find(&table, capability->object);
    if (found == NULL || found->kind != kind) {
        return -KERNEL_ERROR_INVALID_HANDLE;
    }
    if ((capability->rights & rights) != rights) {
        return -KERNEL_ERROR_ACCESS_DENIED;
    }
    *object = found;
    return KERNEL_OK;
}

int64_t capability_transferable_rights(uint32_t space, uint64_t handle, uint32_t *rights)
{
    struct capability capability;
    const struct kernel_object *object;

    if (!capability_find(&registry, space, handle, &capability)) {
        return -KERNEL_ERROR_INVALID_HANDLE;
    }
    object = object_find(&table, capability.object);
    if (object == NULL || object->kind == OBJECT_REPLY ||
        (capability.rights & RIGHT_DELEGATE) == 0) {
        return -KERNEL_ERROR_ACCESS_DENIED;
    }
    *rights = capability.rights & ~RIGHT_RECEIVE;
    return KERNEL_OK;
}

int64_t capability_delegate(uint32_t space, uint64_t handle, uint32_t rights, uint32_t destination)
{
    uint32_t transferable;
    int64_t status = capability_transferable_rights(space, handle, &transferable);

    if (status != KERNEL_OK) {
        return status;
    }
    if ((rights & RIGHT_RECEIVE) != 0) {
        return -KERNEL_ERROR_ACCESS_DENIED;
    }
    return capability_derive(&registry, space, handle, rights, destination);
}
