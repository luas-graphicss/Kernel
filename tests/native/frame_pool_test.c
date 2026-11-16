#include <stdint.h>

#include "check.h"
#include "kernel/memory/frame_pool.h"

#define POOL_BASE 0x80000000ull
#define POOL_FRAMES 2048u
#define LARGEST_BLOCK_FRAMES (1u << FRAME_MAX_ORDER)
#define TRACKED_BLOCKS 64u

static struct frame_record records[POOL_FRAMES];

struct block {
    uint64_t address;
    uint32_t order;
};

static struct memory_range frames(uint32_t first, uint32_t count)
{
    return (struct memory_range){
        .base = POOL_BASE + first * FRAME_BYTES,
        .length = count * FRAME_BYTES,
    };
}

static struct frame_pool pool_with(uint32_t usable)
{
    struct frame_pool pool;

    CHECK(frame_pool_init(&pool, POOL_BASE, records, POOL_FRAMES));
    CHECK(frame_pool_add_usable(&pool, frames(0, usable)) == FRAME_OK);
    return pool;
}

static uint32_t free_blocks(const struct frame_pool *pool, uint32_t order)
{
    uint32_t count = 0;

    for (uint32_t index = pool->free_heads[order]; index != FRAME_NO_LINK;
         index = pool->records[index].next) {
        count++;
    }
    return count;
}

static void test_initialization_rejects_unusable_arguments(void)
{
    struct frame_pool pool;

    CHECK(!frame_pool_init(&pool, POOL_BASE + 1u, records, POOL_FRAMES));
    CHECK(!frame_pool_init(&pool, POOL_BASE, NULL, POOL_FRAMES));
    CHECK(!frame_pool_init(&pool, POOL_BASE, records, 0));
    CHECK(frame_pool_init(&pool, POOL_BASE, records, POOL_FRAMES));
    CHECK(pool.free_frames == 0 && pool.usable_frames == 0);
}

static void test_usable_ranges_are_trimmed_to_whole_frames(void)
{
    struct frame_pool pool;
    struct memory_range ragged = {.base = POOL_BASE + 100u, .length = 3u * FRAME_BYTES};

    CHECK(frame_pool_init(&pool, POOL_BASE, records, POOL_FRAMES));
    CHECK(frame_pool_add_usable(&pool, ragged) == FRAME_OK);
    CHECK(pool.usable_frames == 2 && pool.free_frames == 2);
    CHECK(frame_pool_add_usable(&pool, frames(1, 1)) == FRAME_BAD_RANGE);
    CHECK(frame_pool_add_usable(&pool, frames(POOL_FRAMES - 1u, 2)) == FRAME_BAD_RANGE);
    CHECK(frame_pool_add_usable(&pool, (struct memory_range){POOL_BASE - FRAME_BYTES,
                                                              FRAME_BYTES}) == FRAME_BAD_RANGE);
    CHECK(frame_pool_add_usable(&pool, (struct memory_range){UINT64_MAX, 2}) == FRAME_BAD_RANGE);
    CHECK(pool.usable_frames == 2);
}

static void test_allocation_splits_and_release_merges(void)
{
    struct frame_pool pool = pool_with(LARGEST_BLOCK_FRAMES);
    uint64_t address = 0;

    CHECK(free_blocks(&pool, FRAME_MAX_ORDER) == 1);
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_OK);
    CHECK(address == POOL_BASE);
    CHECK(pool.free_frames == LARGEST_BLOCK_FRAMES - 1u);
    for (uint32_t order = 0; order < FRAME_MAX_ORDER; order++) {
        CHECK(free_blocks(&pool, order) == 1);
    }
    CHECK(free_blocks(&pool, FRAME_MAX_ORDER) == 0);

    CHECK(frame_pool_free(&pool, address, 0) == FRAME_OK);
    CHECK(pool.free_frames == LARGEST_BLOCK_FRAMES);
    for (uint32_t order = 0; order < FRAME_MAX_ORDER; order++) {
        CHECK(free_blocks(&pool, order) == 0);
    }
    CHECK(free_blocks(&pool, FRAME_MAX_ORDER) == 1);
}

static void test_blocks_are_aligned_and_disjoint(void)
{
    struct frame_pool pool = pool_with(POOL_FRAMES);
    struct block blocks[TRACKED_BLOCKS];
    uint32_t count = 0;

    for (uint32_t round = 0; round < TRACKED_BLOCKS; round++) {
        uint32_t order = round % 5u;

        if (frame_pool_allocate(&pool, order, FRAME_FOR_PROCESS, &blocks[count].address) !=
            FRAME_OK) {
            break;
        }
        blocks[count].order = order;
        count++;
    }
    CHECK(count == TRACKED_BLOCKS);
    for (uint32_t first = 0; first < count; first++) {
        uint64_t first_bytes = FRAME_BYTES << blocks[first].order;

        CHECK((blocks[first].address - POOL_BASE) % first_bytes == 0);
        for (uint32_t second = first + 1u; second < count; second++) {
            uint64_t second_bytes = FRAME_BYTES << blocks[second].order;

            CHECK(blocks[first].address + first_bytes <= blocks[second].address ||
                  blocks[second].address + second_bytes <= blocks[first].address);
        }
    }
    for (uint32_t index = 0; index < count; index += 2u) {
        CHECK(frame_pool_free(&pool, blocks[index].address, blocks[index].order) == FRAME_OK);
    }
    for (uint32_t index = 1; index < count; index += 2u) {
        CHECK(frame_pool_free(&pool, blocks[index].address, blocks[index].order) == FRAME_OK);
    }
    CHECK(pool.free_frames == POOL_FRAMES);
    CHECK(free_blocks(&pool, FRAME_MAX_ORDER) == POOL_FRAMES / LARGEST_BLOCK_FRAMES);
}

static void test_release_is_validated(void)
{
    struct frame_pool pool = pool_with(LARGEST_BLOCK_FRAMES);
    uint64_t address = 0;

    CHECK(frame_pool_allocate(&pool, 2, FRAME_FOR_PROCESS, &address) == FRAME_OK);
    CHECK(frame_pool_free(&pool, address, 1) == FRAME_NOT_ALLOCATED);
    CHECK(frame_pool_free(&pool, address + FRAME_BYTES, 0) == FRAME_NOT_ALLOCATED);
    CHECK(frame_pool_free(&pool, address + 1u, 2) == FRAME_BAD_RANGE);
    CHECK(frame_pool_free(&pool, POOL_BASE - FRAME_BYTES, 0) == FRAME_BAD_RANGE);
    CHECK(frame_pool_free(&pool, POOL_BASE + POOL_FRAMES * FRAME_BYTES, 0) == FRAME_BAD_RANGE);
    CHECK(frame_pool_free(&pool, address, FRAME_MAX_ORDER + 1u) == FRAME_BAD_ORDER);
    CHECK(frame_pool_free(&pool, address, 2) == FRAME_OK);
    CHECK(frame_pool_free(&pool, address, 2) == FRAME_NOT_ALLOCATED);
    CHECK(pool.free_frames == LARGEST_BLOCK_FRAMES);
}

static void test_exhaustion_is_reported_and_recoverable(void)
{
    struct frame_pool pool = pool_with(16);
    uint64_t held[16];
    uint64_t extra = 0;

    for (uint32_t index = 0; index < 16; index++) {
        CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_SUPERVISOR, &held[index]) == FRAME_OK);
    }
    CHECK(pool.free_frames == 0);
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_SUPERVISOR, &extra) == FRAME_OUT_OF_MEMORY);
    CHECK(frame_pool_allocate(&pool, FRAME_MAX_ORDER + 1u, FRAME_FOR_SUPERVISOR, &extra) ==
          FRAME_BAD_ORDER);
    CHECK(pool.refused_allocations == 1);
    CHECK(frame_pool_free(&pool, held[7], 0) == FRAME_OK);
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_SUPERVISOR, &extra) == FRAME_OK);
    CHECK(extra == held[7]);
}

static void test_reserve_is_kept_from_processes(void)
{
    struct frame_pool pool = pool_with(32);
    uint64_t address = 0;
    uint32_t granted = 0;

    pool.reserve_frames = 8;
    while (frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_OK) {
        granted++;
    }
    CHECK(granted == 24);
    CHECK(pool.free_frames == 8);
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_RESERVE_PROTECTED);
    CHECK(frame_pool_allocate(&pool, 3, FRAME_FOR_PROCESS, &address) == FRAME_RESERVE_PROTECTED);
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_SUPERVISOR, &address) == FRAME_OK);
    CHECK(pool.free_frames == 7);
}

static void test_injected_failure_refuses_later_allocations(void)
{
    struct frame_pool pool = pool_with(32);
    uint64_t address = 0;

    pool.allocations_before_failure = 2;
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_OK);
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_OK);
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_OUT_OF_MEMORY);
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_OUT_OF_MEMORY);
    CHECK(pool.free_frames == 30);
    pool.allocations_before_failure = FRAME_UNLIMITED_ALLOCATIONS;
    CHECK(frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_OK);
}

static void test_ragged_range_yields_every_frame(void)
{
    struct frame_pool pool;
    uint64_t address = 0;
    uint32_t granted = 0;

    CHECK(frame_pool_init(&pool, POOL_BASE, records, POOL_FRAMES));
    CHECK(frame_pool_add_usable(&pool, frames(3, 17)) == FRAME_OK);
    CHECK(frame_pool_add_usable(&pool, frames(20, 12)) == FRAME_OK);
    CHECK(pool.usable_frames == 29);
    while (frame_pool_allocate(&pool, 0, FRAME_FOR_PROCESS, &address) == FRAME_OK) {
        CHECK(address >= POOL_BASE + 3u * FRAME_BYTES && address < POOL_BASE + 32u * FRAME_BYTES);
        granted++;
    }
    CHECK(granted == 29);
}

static void test_order_covers_the_requested_bytes(void)
{
    uint32_t order = 99;

    CHECK(frame_order_for_bytes(1, &order) && order == 0);
    CHECK(frame_order_for_bytes(FRAME_BYTES, &order) && order == 0);
    CHECK(frame_order_for_bytes(FRAME_BYTES + 1u, &order) && order == 1);
    CHECK(frame_order_for_bytes(FRAME_BYTES << FRAME_MAX_ORDER, &order) && order == FRAME_MAX_ORDER);
    CHECK(!frame_order_for_bytes((FRAME_BYTES << FRAME_MAX_ORDER) + 1u, &order));
    CHECK(!frame_order_for_bytes(0, &order));
    CHECK(!frame_order_for_bytes(UINT64_MAX, &order));
}

int main(void)
{
    test_initialization_rejects_unusable_arguments();
    test_usable_ranges_are_trimmed_to_whole_frames();
    test_allocation_splits_and_release_merges();
    test_blocks_are_aligned_and_disjoint();
    test_release_is_validated();
    test_exhaustion_is_reported_and_recoverable();
    test_reserve_is_kept_from_processes();
    test_injected_failure_refuses_later_allocations();
    test_ragged_range_yields_every_frame();
    test_order_covers_the_requested_bytes();
    return check_finish("frame-pool");
}
