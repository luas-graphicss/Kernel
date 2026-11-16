#ifndef KERNEL_OBJECTS_OBJECT_TABLE_H
#define KERNEL_OBJECTS_OBJECT_TABLE_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/objects/slot_table.h"

#define OBJECT_NO_OWNER UINT32_MAX

struct kernel_object {
    uint32_t kind;
    uint32_t references;
    uint32_t owner;
    uint32_t state;
    uint64_t payload;
    uint64_t detail;
};

typedef void (*object_disposer)(void *context, uint64_t handle, struct kernel_object object);

struct object_table {
    struct slot_table slots;
    struct kernel_object *objects;
    object_disposer dispose;
    void *context;
};

void object_table_init(struct object_table *table, struct slot_record *records,
                       struct kernel_object *objects, uint32_t capacity, object_disposer dispose,
                       void *context);
uint64_t object_create(struct object_table *table, uint32_t kind, uint32_t owner,
                       uint64_t payload);
struct kernel_object *object_find(struct object_table *table, uint64_t handle);
bool object_retain(struct object_table *table, uint64_t handle);
bool object_release(struct object_table *table, uint64_t handle);

#endif
