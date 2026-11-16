#include "kernel/memory/frame_pool.h"

#include <stddef.h>

static uint32_t block_frames(uint32_t order)
{
    return 1u << order;
}

static void list_insert(struct frame_pool *pool, uint32_t index, uint32_t order)
{
    struct frame_record *record = &pool->records[index];
    uint32_t head = pool->free_heads[order];

    record->state = FRAME_FREE;
    record->order = (uint8_t)order;
    record->previous = FRAME_NO_LINK;
    record->next = head;
    if (head != FRAME_NO_LINK) {
        pool->records[head].previous = index;
    }
    pool->free_heads[order] = index;
}

static void list_remove(struct frame_pool *pool, uint32_t index)
{
    const struct frame_record *record = &pool->records[index];

    if (record->previous != FRAME_NO_LINK) {
        pool->records[record->previous].next = record->next;
    } else {
        pool->free_heads[record->order] = record->next;
    }
    if (record->next != FRAME_NO_LINK) {
        pool->records[record->next].previous = record->previous;
    }
}

static bool buddy_is_free(const struct frame_pool *pool, uint32_t buddy, uint32_t order)
{
    return buddy < pool->frame_count && pool->records[buddy].state == FRAME_FREE &&
           pool->records[buddy].order == order;
}

static void release_block(struct frame_pool *pool, uint32_t index, uint32_t order)
{
    pool->free_frames += block_frames(order);
    while (order < FRAME_MAX_ORDER) {
        uint32_t buddy = index ^ block_frames(order);

        if (!buddy_is_free(pool, buddy, order)) {
            break;
        }
        list_remove(pool, buddy);
        if (buddy < index) {
            pool->records[index].state = FRAME_INTERIOR;
            index = buddy;
        } else {
            pool->records[buddy].state = FRAME_INTERIOR;
        }
        order++;
    }
    list_insert(pool, index, order);
}

static bool frame_index(const struct frame_pool *pool, uint64_t address, uint32_t *index)
{
    uint64_t offset;

    if (address < pool->base || (address - pool->base) % FRAME_BYTES != 0) {
        return false;
    }
    offset = (address - pool->base) / FRAME_BYTES;
    if (offset >= pool->frame_count) {
        return false;
    }
    *index = (uint32_t)offset;
    return true;
}

static uint32_t largest_order_at(uint32_t index, uint32_t available)
{
    uint32_t order = FRAME_MAX_ORDER;

    while (order > 0 && (index % block_frames(order) != 0 || block_frames(order) > available)) {
        order--;
    }
    return order;
}

static bool injected_failure(struct frame_pool *pool)
{
    if (pool->allocations_before_failure == FRAME_UNLIMITED_ALLOCATIONS) {
        return false;
    }
    if (pool->allocations_before_failure == 0) {
        return true;
    }
    pool->allocations_before_failure--;
    return false;
}

bool frame_pool_init(struct frame_pool *pool, uint64_t base, struct frame_record *records,
                     uint32_t frame_count)
{
    if (base % FRAME_BYTES != 0 || records == NULL || frame_count == 0) {
        return false;
    }
    *pool = (struct frame_pool){
        .base = base,
        .frame_count = frame_count,
        .records = records,
        .allocations_before_failure = FRAME_UNLIMITED_ALLOCATIONS,
    };
    for (uint32_t order = 0; order < FRAME_ORDERS; order++) {
        pool->free_heads[order] = FRAME_NO_LINK;
    }
    for (uint32_t index = 0; index < frame_count; index++) {
        records[index] = (struct frame_record){
            .next = FRAME_NO_LINK,
            .previous = FRAME_NO_LINK,
            .state = FRAME_UNUSABLE,
        };
    }
    return true;
}

enum frame_status frame_pool_add_usable(struct frame_pool *pool, struct memory_range range)
{
    uint64_t pool_bytes = (uint64_t)pool->frame_count * FRAME_BYTES;
    uint64_t end;
    uint64_t first;
    uint64_t last;

    if (!memory_range_end(range, &end) || range.base < pool->base ||
        end - pool->base > pool_bytes) {
        return FRAME_BAD_RANGE;
    }
    first = (range.base - pool->base + FRAME_BYTES - 1u) / FRAME_BYTES;
    last = (end - pool->base) / FRAME_BYTES;
    for (uint64_t index = first; index < last; index++) {
        if (pool->records[index].state != FRAME_UNUSABLE) {
            return FRAME_BAD_RANGE;
        }
    }
    while (first < last) {
        uint32_t index = (uint32_t)first;
        uint32_t order = largest_order_at(index, (uint32_t)(last - first));

        for (uint32_t offset = 0; offset < block_frames(order); offset++) {
            pool->records[index + offset].state = FRAME_INTERIOR;
        }
        release_block(pool, index, order);
        pool->usable_frames += block_frames(order);
        first += block_frames(order);
    }
    return FRAME_OK;
}

enum frame_status frame_pool_allocate(struct frame_pool *pool, uint32_t order,
                                      enum frame_purpose purpose, uint64_t *address)
{
    uint32_t available = order;
    uint32_t index;
    uint64_t needed;

    if (order > FRAME_MAX_ORDER) {
        return FRAME_BAD_ORDER;
    }
    needed = block_frames(order);
    if (injected_failure(pool)) {
        pool->refused_allocations++;
        return FRAME_OUT_OF_MEMORY;
    }
    if (purpose == FRAME_FOR_PROCESS &&
        (pool->free_frames < needed || pool->free_frames - needed < pool->reserve_frames)) {
        pool->refused_allocations++;
        return FRAME_RESERVE_PROTECTED;
    }
    while (available <= FRAME_MAX_ORDER && pool->free_heads[available] == FRAME_NO_LINK) {
        available++;
    }
    if (available > FRAME_MAX_ORDER) {
        pool->refused_allocations++;
        return FRAME_OUT_OF_MEMORY;
    }
    index = pool->free_heads[available];
    list_remove(pool, index);
    while (available > order) {
        available--;
        list_insert(pool, index + block_frames(available), available);
    }
    pool->records[index].state = FRAME_ALLOCATED;
    pool->records[index].order = (uint8_t)order;
    pool->free_frames -= needed;
    *address = pool->base + (uint64_t)index * FRAME_BYTES;
    return FRAME_OK;
}

enum frame_status frame_pool_free(struct frame_pool *pool, uint64_t address, uint32_t order)
{
    uint32_t index;

    if (order > FRAME_MAX_ORDER) {
        return FRAME_BAD_ORDER;
    }
    if (!frame_index(pool, address, &index)) {
        return FRAME_BAD_RANGE;
    }
    if (pool->records[index].state != FRAME_ALLOCATED || pool->records[index].order != order) {
        return FRAME_NOT_ALLOCATED;
    }
    pool->records[index].state = FRAME_INTERIOR;
    release_block(pool, index, order);
    return FRAME_OK;
}

bool frame_order_for_bytes(uint64_t bytes, uint32_t *order)
{
    uint32_t candidate = 0;

    if (bytes == 0 || bytes > FRAME_BYTES << FRAME_MAX_ORDER) {
        return false;
    }
    while (FRAME_BYTES << candidate < bytes) {
        candidate++;
    }
    *order = candidate;
    return true;
}
