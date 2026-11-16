#include "kernel/memory/buffer.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/memory/buffer_pins.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/memory/string.h"
#include "kernel/objects/kernel_objects.h"

#define BUFFER_CAPACITY 64u
#define MAPPING_TABLE_FRAMES 2u

struct buffer {
    bool used;
    bool alive;
    bool disposed;
    uint32_t owner;
    uint32_t order;
    uint32_t pins;
    uint64_t owner_handle;
    uint64_t base;
    uint64_t bytes;
};

static struct buffer buffers[BUFFER_CAPACITY];
static uint64_t live;
static uint64_t pinned;

static void release_frames(struct buffer *buffer)
{
    frame_pool_free(physical_memory_pool(), buffer->base, buffer->order);
    if (buffer->disposed) {
        buffer->used = false;
        live--;
    }
}

static uint32_t mapping_rights(const struct buffer_mapping *mapping)
{
    return mapping->writable ? RIGHT_MAP | RIGHT_READ | RIGHT_WRITE : RIGHT_MAP | RIGHT_READ;
}

static void remove_mapping(struct process *process, struct buffer_mapping *mapping)
{
    uint64_t object = mapping->object;

    address_space_unmap(&process->space, mapping->address, mapping->bytes);
    mapping->used = false;
    object_release(kernel_object_table(), object);
}

static void unmap_everywhere(uint32_t buffer)
{
    for (uint32_t index = 0; index < process_capacity(); index++) {
        struct process *process = process_at(index);

        if (process->state == PROCESS_FREE) {
            continue;
        }
        for (uint32_t slot = 0; slot < PROCESS_BUFFER_MAPPINGS; slot++) {
            if (process->mappings[slot].used && process->mappings[slot].buffer == buffer) {
                remove_mapping(process, &process->mappings[slot]);
            }
        }
    }
}

static void destroy(uint32_t index)
{
    struct buffer *buffer = &buffers[index];
    struct process *owner = process_at(buffer->owner);

    if (!buffer->alive) {
        return;
    }
    buffer->alive = false;
    unmap_everywhere(index);
    if (owner != NULL && owner->handle == buffer->owner_handle) {
        owner->buffer_frames -= buffer->bytes / FRAME_BYTES;
    }
    if (buffer->pins == 0) {
        release_frames(buffer);
    }
}

void buffer_table_init(void)
{
    live = 0;
    pinned = 0;
    for (uint32_t index = 0; index < BUFFER_CAPACITY; index++) {
        buffers[index] = (struct buffer){0};
    }
}

int64_t buffer_allocate(struct process *owner, uint64_t bytes)
{
    uint32_t order;
    uint32_t slot = 0;
    uint64_t frames;
    uint64_t base;

    if (bytes == 0) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    if (bytes > BUFFER_MAX_BYTES || !frame_order_for_bytes(bytes, &order)) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    frames = 1ull << order;
    while (slot < BUFFER_CAPACITY && buffers[slot].used) {
        slot++;
    }
    if (slot == BUFFER_CAPACITY ||
        process_memory_frames(owner) + frames > owner->memory_quota_frames) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    if (frame_pool_allocate(physical_memory_pool(), order, FRAME_FOR_PROCESS, &base) != FRAME_OK) {
        return -KERNEL_ERROR_OUT_OF_MEMORY;
    }
    memset((void *)(uintptr_t)base, 0, (size_t)(frames * FRAME_BYTES));
    buffers[slot] = (struct buffer){
        .used = true,
        .alive = true,
        .owner = owner->index,
        .order = order,
        .owner_handle = owner->handle,
        .base = base,
        .bytes = frames * FRAME_BYTES,
    };
    owner->buffer_frames += frames;
    live++;
    return slot;
}

void buffer_dispose(uint32_t index)
{
    struct buffer *buffer = &buffers[index];

    if (!buffer->used || buffer->disposed) {
        return;
    }
    destroy(index);
    buffer->disposed = true;
    if (buffer->pins == 0) {
        buffer->used = false;
        live--;
    }
}

bool buffer_pin(uint32_t index, uint64_t offset, uint64_t length, uint64_t *physical)
{
    struct buffer *buffer = index < BUFFER_CAPACITY ? &buffers[index] : NULL;

    if (buffer == NULL || !buffer->used || !buffer->alive || length == 0 ||
        offset > buffer->bytes || length > buffer->bytes - offset) {
        return false;
    }
    if (buffer->pins == 0) {
        pinned++;
    }
    buffer->pins++;
    *physical = buffer->base + offset;
    return true;
}

void buffer_unpin(uint32_t index)
{
    struct buffer *buffer = &buffers[index];

    buffer->pins--;
    if (buffer->pins != 0) {
        return;
    }
    pinned--;
    if (!buffer->alive) {
        release_frames(buffer);
    }
}

uint64_t buffer_pinned_count(void)
{
    return pinned;
}

void buffer_destroy_owned(const struct process *owner)
{
    for (uint32_t index = 0; index < BUFFER_CAPACITY; index++) {
        if (buffers[index].used && buffers[index].owner_handle == owner->handle) {
            destroy(index);
        }
    }
}

int64_t buffer_map(struct process *process, uint32_t index, uint64_t object, bool writable,
                   uint64_t *address, uint64_t *bytes)
{
    const struct buffer *buffer = &buffers[index];
    uint64_t tables = buffer->bytes / PAGE_LARGE_BYTES + MAPPING_TABLE_FRAMES;
    uint64_t permissions = writable ? PAGE_READ | PAGE_WRITE : PAGE_READ;
    uint32_t slot = 0;
    uint64_t base;

    if (!buffer->used || !buffer->alive) {
        return -KERNEL_ERROR_PEER_CLOSED;
    }
    while (slot < PROCESS_BUFFER_MAPPINGS && process->mappings[slot].used) {
        slot++;
    }
    if (slot == PROCESS_BUFFER_MAPPINGS ||
        process_memory_frames(process) + tables > process->memory_quota_frames) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    base = process->space.user.base + BUFFER_WINDOW_OFFSET + slot * BUFFER_WINDOW_STRIDE;
    if (address_space_map_borrowed(&process->space, base, buffer->base, buffer->bytes,
                                   permissions) != PAGE_OK) {
        return -KERNEL_ERROR_OUT_OF_MEMORY;
    }
    object_retain(kernel_object_table(), object);
    process->mappings[slot] = (struct buffer_mapping){
        .used = true,
        .writable = writable,
        .buffer = index,
        .object = object,
        .address = base,
        .bytes = buffer->bytes,
    };
    *address = base;
    *bytes = buffer->bytes;
    return KERNEL_OK;
}

int64_t buffer_unmap(struct process *process, uint64_t address)
{
    for (uint32_t slot = 0; slot < PROCESS_BUFFER_MAPPINGS; slot++) {
        if (process->mappings[slot].used && process->mappings[slot].address == address) {
            remove_mapping(process, &process->mappings[slot]);
            return KERNEL_OK;
        }
    }
    return -KERNEL_ERROR_INVALID_ARGUMENT;
}

void buffer_unmap_all(struct process *process)
{
    for (uint32_t slot = 0; slot < PROCESS_BUFFER_MAPPINGS; slot++) {
        if (process->mappings[slot].used) {
            remove_mapping(process, &process->mappings[slot]);
        }
    }
}

void buffer_revoke_mappings(struct process *process, uint64_t object)
{
    for (uint32_t slot = 0; slot < PROCESS_BUFFER_MAPPINGS; slot++) {
        struct buffer_mapping *mapping = &process->mappings[slot];

        if (mapping->used && mapping->object == object &&
            !capability_space_holds(kernel_capabilities(), process->index, object,
                                    mapping_rights(mapping))) {
            remove_mapping(process, mapping);
        }
    }
}

uint64_t buffer_live_count(void)
{
    return live;
}
