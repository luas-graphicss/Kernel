#include "kernel/objects/object_table.h"

#include <stddef.h>

void object_table_init(struct object_table *table, struct slot_record *records,
                       struct kernel_object *objects, uint32_t capacity, object_disposer dispose,
                       void *context)
{
    slot_table_init(&table->slots, records, capacity, SLOT_MAX_GENERATION);
    table->objects = objects;
    table->dispose = dispose;
    table->context = context;
}

uint64_t object_create(struct object_table *table, uint32_t kind, uint32_t owner, uint64_t payload)
{
    uint64_t handle = slot_table_allocate(&table->slots);

    if (handle == SLOT_INVALID_HANDLE) {
        return SLOT_INVALID_HANDLE;
    }
    table->objects[handle & SLOT_INDEX_MASK] = (struct kernel_object){
        .kind = kind,
        .references = 1,
        .owner = owner,
        .payload = payload,
    };
    return handle;
}

struct kernel_object *object_find(struct object_table *table, uint64_t handle)
{
    uint32_t index;

    if (!slot_table_resolve(&table->slots, handle, &index)) {
        return NULL;
    }
    return &table->objects[index];
}

bool object_retain(struct object_table *table, uint64_t handle)
{
    struct kernel_object *object = object_find(table, handle);

    if (object == NULL || object->references == UINT32_MAX) {
        return false;
    }
    object->references++;
    return true;
}

bool object_release(struct object_table *table, uint64_t handle)
{
    struct kernel_object *object = object_find(table, handle);
    struct kernel_object disposed;

    if (object == NULL) {
        return false;
    }
    object->references--;
    if (object->references != 0) {
        return true;
    }
    disposed = *object;
    slot_table_release(&table->slots, handle);
    if (table->dispose != NULL) {
        table->dispose(table->context, handle, disposed);
    }
    return true;
}
