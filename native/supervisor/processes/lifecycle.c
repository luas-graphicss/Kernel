#include "kernel/processes/process.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/diagnostics/halt.h"
#include "kernel/ipc/call.h"
#include "kernel/memory/buffer.h"
#include "kernel/memory/endian.h"
#include "kernel/memory/kernel_space.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/memory/string.h"
#include "kernel/objects/kernel_objects.h"
#include "kernel/processes/program.h"
#include "kernel/processes/spawn.h"

#define SYSTEM_RIGHTS (RIGHT_ADMIN | RIGHT_READ | RIGHT_DELEGATE)
#define DOUBLE_WORD_BYTES 8u

struct startup_handles {
    uint64_t values[PROCESS_GRANTS];
    uint32_t count;
};

static void put(uint8_t *block, uint32_t offset, uint64_t value)
{
    little_endian_write(block + offset, DOUBLE_WORD_BYTES, value);
}

static int64_t grant_system(const struct process *process, struct startup_handles *handles)
{
    int64_t handle;

    object_retain(kernel_object_table(), kernel_system_object());
    handle = capability_install(kernel_capabilities(), process->index, kernel_system_object(),
                                SYSTEM_RIGHTS);
    if (handle < 0) {
        object_release(kernel_object_table(), kernel_system_object());
        return handle;
    }
    handles->values[handles->count] = (uint64_t)handle;
    handles->count++;
    return KERNEL_OK;
}

static int64_t install_grants(const struct process *process, const struct process_request *request,
                              struct startup_handles *handles)
{
    if (request->grants_system) {
        int64_t status = grant_system(process, handles);

        if (status != KERNEL_OK) {
            return status;
        }
    }
    for (uint32_t index = 0; index < request->grant_count; index++) {
        int64_t handle = capability_delegate(request->parent, request->grants[index].handle,
                                             request->grants[index].rights, process->index);

        if (handle < 0) {
            return handle;
        }
        if (handles->count == PROCESS_GRANTS) {
            return -KERNEL_ERROR_LIMIT_EXCEEDED;
        }
        handles->values[handles->count] = (uint64_t)handle;
        handles->count++;
    }
    return KERNEL_OK;
}

static int64_t prepare_entry(struct process *process, const struct process_request *request,
                             const struct user_layout *layout,
                             const struct startup_handles *handles)
{
    uint8_t block[STARTUP_BYTES] = {0};
    uint64_t address = layout->stack_top - STARTUP_BYTES;
    struct trap_frame *frame = &process->context.frame;

    put(block, STARTUP_FIELD_HEAP_START, layout->heap_base);
    put(block, STARTUP_FIELD_HEAP_END, layout->heap_end);
    put(block, STARTUP_FIELD_STACK_BOTTOM, layout->stack_bottom);
    put(block, STARTUP_FIELD_IDENTITY, process->handle);
    put(block, STARTUP_FIELD_HANDLE_COUNT, handles->count);
    for (uint32_t index = 0; index < handles->count; index++) {
        put(block, STARTUP_FIELD_HANDLES + index * DOUBLE_WORD_BYTES, handles->values[index]);
    }
    put(block, STARTUP_FIELD_NAME_LENGTH, request->name_length);
    put(block, STARTUP_FIELD_ARGUMENT_LENGTH, request->argument_length);
    memcpy(block + STARTUP_FIELD_NAME, request->name, request->name_length);
    if (request->argument_length != 0) {
        memcpy(block + STARTUP_FIELD_ARGUMENT, request->argument, request->argument_length);
    }
    if (!address_space_fill(&process->space, address, block, STARTUP_BYTES)) {
        return -KERNEL_ERROR_BAD_ADDRESS;
    }
    frame->program_counter = program_image()->entry;
    frame->status = user_context_status();
    frame->registers[REGISTER_STACK_POINTER] = address;
    frame->registers[REGISTER_ARGUMENT_FIRST] = address;
    return KERNEL_OK;
}

static int64_t build(struct process *process, const struct process_request *request,
                     const struct user_layout *layout)
{
    struct startup_handles handles = {0};
    int64_t status;

    process->object =
        object_create(kernel_object_table(), OBJECT_PROCESS, OBJECT_NO_OWNER, process->handle);
    if (process->object == SLOT_INVALID_HANDLE) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    if (!capability_space_open(kernel_capabilities(), process->index, request->capability_limit)) {
        kernel_panic("capability-space-busy");
    }
    if (address_space_create(&process->space, physical_memory_pool(), kernel_space_tables(),
                             program_address_range()) != PAGE_OK ||
        program_load(&process->space, layout) != PAGE_OK) {
        return -KERNEL_ERROR_OUT_OF_MEMORY;
    }
    status = install_grants(process, request, &handles);
    if (status != KERNEL_OK) {
        return status;
    }
    return prepare_entry(process, request, layout, &handles);
}

static void discard(struct process *process)
{
    capability_space_close(kernel_capabilities(), process->index);
    address_space_destroy(&process->space);
    if (process->object == SLOT_INVALID_HANDLE) {
        process_free(process);
        return;
    }
    object_release(kernel_object_table(), process->object);
}

int64_t process_create(const struct process_request *request)
{
    const struct user_image *image = program_image();
    struct user_layout layout;
    struct process *process;
    uint64_t heap_bytes;
    int64_t status;

    if (image == NULL) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    if (request->name_length == 0 || request->name_length > PROCESS_NAME_BYTES ||
        request->argument_length > PROCESS_ARGUMENT_BYTES || request->capability_limit == 0) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    heap_bytes = request->heap_bytes != 0 ? request->heap_bytes : image->heap_bytes;
    if (heap_bytes > PROFILE_PROCESS_HEAP_BYTES ||
        !user_layout_compute(image, program_region(), heap_bytes, &layout) ||
        layout.private_frames + layout.table_frames > request->memory_quota_frames) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    process = process_allocate();
    if (process == NULL) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    process->memory_quota_frames = request->memory_quota_frames;
    process->ipc_quota_bytes = request->ipc_quota_bytes;
    status = build(process, request, &layout);
    if (status != KERNEL_OK) {
        discard(process);
        return status;
    }
    process->state = PROCESS_READY;
    return (int64_t)process->handle;
}

void process_terminate(struct process *process, uint32_t reason, uint64_t value)
{
    if (process->state == PROCESS_FREE || process->state == PROCESS_DYING) {
        return;
    }
    if (process->state == PROCESS_BLOCKED && process->wait.kind == WAIT_REPLY) {
        call_abandon(process);
    }
    process->wait = (struct process_wait){.depends_on = PROCESS_NONE};
    process->state = PROCESS_DYING;
    process->exit_reason = reason;
    process->exit_value = value;
    spawn_cancel(process);
    buffer_unmap_all(process);
    capability_space_close(kernel_capabilities(), process->index);
    buffer_destroy_owned(process);
    address_space_destroy(&process->space);
    wait_wake_exit_waiters(process->handle);
}

void process_reap(uint64_t handle)
{
    struct process *process = process_find(handle);

    if (process == NULL) {
        return;
    }
    if (process->state != PROCESS_DYING && process->state != PROCESS_NEW) {
        kernel_panic("live-process-released");
    }
    process_free(process);
}
