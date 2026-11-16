#ifndef KERNEL_OBJECTS_SLOT_TABLE_H
#define KERNEL_OBJECTS_SLOT_TABLE_H

#include <stdbool.h>
#include <stdint.h>

#define SLOT_INDEX_BITS 24u
#define SLOT_INDEX_MASK ((1ull << SLOT_INDEX_BITS) - 1u)
#define SLOT_GENERATION_BITS 32u
#define SLOT_FIRST_GENERATION 1u
#define SLOT_MAX_GENERATION UINT32_MAX
#define SLOT_NO_INDEX UINT32_MAX
#define SLOT_INVALID_HANDLE 0ull

struct slot_record {
    uint32_t generation;
    uint32_t next_free;
    bool occupied;
};

struct slot_table {
    struct slot_record *records;
    uint32_t capacity;
    uint32_t free_head;
    uint32_t live;
    uint32_t retired;
    uint32_t max_generation;
};

void slot_table_init(struct slot_table *table, struct slot_record *records, uint32_t capacity,
                     uint32_t max_generation);
uint64_t slot_table_allocate(struct slot_table *table);
bool slot_table_resolve(const struct slot_table *table, uint64_t handle, uint32_t *index);
bool slot_table_release(struct slot_table *table, uint64_t handle);
uint64_t slot_table_handle_at(const struct slot_table *table, uint32_t index);

#endif
