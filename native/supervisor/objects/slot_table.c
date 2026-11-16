#include "kernel/objects/slot_table.h"

#define RESERVED_SHIFT (SLOT_INDEX_BITS + SLOT_GENERATION_BITS)

static uint64_t pack_handle(uint32_t index, uint32_t generation)
{
    return ((uint64_t)generation << SLOT_INDEX_BITS) | index;
}

void slot_table_init(struct slot_table *table, struct slot_record *records, uint32_t capacity,
                     uint32_t max_generation)
{
    *table = (struct slot_table){
        .records = records,
        .capacity = capacity,
        .free_head = capacity == 0 ? SLOT_NO_INDEX : 0,
        .max_generation = max_generation,
    };
    for (uint32_t index = 0; index < capacity; index++) {
        records[index] = (struct slot_record){
            .generation = SLOT_FIRST_GENERATION,
            .next_free = index + 1u < capacity ? index + 1u : SLOT_NO_INDEX,
        };
    }
}

uint64_t slot_table_allocate(struct slot_table *table)
{
    uint32_t index = table->free_head;
    struct slot_record *record;

    if (index == SLOT_NO_INDEX) {
        return SLOT_INVALID_HANDLE;
    }
    record = &table->records[index];
    table->free_head = record->next_free;
    record->occupied = true;
    table->live++;
    return pack_handle(index, record->generation);
}

bool slot_table_resolve(const struct slot_table *table, uint64_t handle, uint32_t *index)
{
    uint64_t slot = handle & SLOT_INDEX_MASK;
    const struct slot_record *record;

    if (handle == SLOT_INVALID_HANDLE || handle >> RESERVED_SHIFT != 0 || slot >= table->capacity) {
        return false;
    }
    record = &table->records[slot];
    if (!record->occupied || record->generation != handle >> SLOT_INDEX_BITS) {
        return false;
    }
    *index = (uint32_t)slot;
    return true;
}

bool slot_table_release(struct slot_table *table, uint64_t handle)
{
    uint32_t index;
    struct slot_record *record;

    if (!slot_table_resolve(table, handle, &index)) {
        return false;
    }
    record = &table->records[index];
    record->occupied = false;
    table->live--;
    if (record->generation >= table->max_generation) {
        table->retired++;
        return true;
    }
    record->generation++;
    record->next_free = table->free_head;
    table->free_head = index;
    return true;
}

uint64_t slot_table_handle_at(const struct slot_table *table, uint32_t index)
{
    if (index >= table->capacity || !table->records[index].occupied) {
        return SLOT_INVALID_HANDLE;
    }
    return pack_handle(index, table->records[index].generation);
}
