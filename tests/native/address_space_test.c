#include <stdint.h>
#include <string.h>

#include "check.h"
#include "frame_arena.h"
#include "kernel/memory/address_space.h"

#define USER_BASE PAGE_ROOT_SPAN
#define USER_BYTES 0x1000000ull
#define SHARED_ADDRESS (2u * PAGE_ROOT_SPAN)
#define SHARED_ROOT_INDEX 2u
#define READ_WRITE (PAGE_READ | PAGE_WRITE)
#define READ_EXECUTE (PAGE_READ | PAGE_EXECUTE)

static const struct memory_range user_region = {.base = USER_BASE, .length = USER_BYTES};

static struct address_space open_space(struct frame_pool *pool)
{
    struct address_space space;

    CHECK(address_space_create(&space, pool, NULL, user_region) == PAGE_OK);
    return space;
}

static uint64_t supervisor_frame(struct frame_pool *pool)
{
    uint64_t frame = 0;

    CHECK(frame_pool_allocate(pool, 0, FRAME_FOR_SUPERVISOR, &frame) == FRAME_OK);
    return frame;
}

static void test_mappings_translate_and_can_be_removed(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct page_tables tables;
    struct page_mapping mapping;
    uint64_t frame = supervisor_frame(pool);

    CHECK(page_tables_create(&tables, pool, FRAME_FOR_SUPERVISOR) == PAGE_OK);
    CHECK(page_tables_map(&tables, USER_BASE, frame, READ_WRITE) == PAGE_OK);
    CHECK(page_tables_lookup(&tables, USER_BASE + 0x123u, &mapping));
    CHECK(mapping.physical == frame + 0x123u);
    CHECK(mapping.bytes == PAGE_BYTES);
    CHECK((mapping.flags & (PAGE_VALID | PAGE_ACCESSED | PAGE_DIRTY)) ==
          (PAGE_VALID | PAGE_ACCESSED | PAGE_DIRTY));
    CHECK(page_tables_map(&tables, USER_BASE, frame, READ_WRITE) == PAGE_ALREADY_MAPPED);
    CHECK(!page_tables_lookup(&tables, USER_BASE + PAGE_BYTES, &mapping));
    CHECK(page_tables_unmap(&tables, USER_BASE, &mapping) == PAGE_OK);
    CHECK(mapping.physical == frame);
    CHECK(page_tables_unmap(&tables, USER_BASE, &mapping) == PAGE_NOT_MAPPED);
    CHECK(!page_tables_lookup(&tables, USER_BASE, &mapping));
}

static void test_writable_pages_are_never_executable(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct page_tables tables;
    struct page_mapping mapping;
    uint64_t frame = supervisor_frame(pool);

    CHECK(page_tables_create(&tables, pool, FRAME_FOR_SUPERVISOR) == PAGE_OK);
    CHECK(page_tables_map(&tables, USER_BASE, frame, READ_WRITE | PAGE_EXECUTE) ==
          PAGE_BAD_PERMISSIONS);
    CHECK(page_tables_map(&tables, USER_BASE, frame, PAGE_WRITE) == PAGE_BAD_PERMISSIONS);
    CHECK(page_tables_map(&tables, USER_BASE, frame, PAGE_WRITE | PAGE_EXECUTE) ==
          PAGE_BAD_PERMISSIONS);
    CHECK(page_tables_map(&tables, USER_BASE, frame, PAGE_USER) == PAGE_BAD_PERMISSIONS);
    CHECK(page_tables_map(&tables, USER_BASE, frame, READ_WRITE | PAGE_VALID) ==
          PAGE_BAD_PERMISSIONS);
    CHECK(!page_tables_lookup(&tables, USER_BASE, &mapping));
    CHECK(page_tables_map(&tables, USER_BASE, frame, READ_EXECUTE) == PAGE_OK);
    CHECK(page_tables_lookup(&tables, USER_BASE, &mapping));
    CHECK((mapping.flags & PAGE_DIRTY) == 0);
}

static void test_addresses_must_be_aligned_and_canonical(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct page_tables tables;
    struct page_mapping mapping;
    uint64_t frame = supervisor_frame(pool);

    CHECK(page_tables_create(&tables, pool, FRAME_FOR_SUPERVISOR) == PAGE_OK);
    CHECK(page_tables_map(&tables, USER_BASE + 1u, frame, PAGE_READ) == PAGE_BAD_ADDRESS);
    CHECK(page_tables_map(&tables, USER_BASE, frame + 8u, PAGE_READ) == PAGE_BAD_ADDRESS);
    CHECK(page_tables_map(&tables, PAGE_VIRTUAL_LIMIT, frame, PAGE_READ) == PAGE_BAD_ADDRESS);
    CHECK(page_tables_map(&tables, UINT64_MAX - PAGE_BYTES + 1u, frame, PAGE_READ) ==
          PAGE_BAD_ADDRESS);
    CHECK(page_tables_unmap(&tables, USER_BASE + 1u, &mapping) == PAGE_BAD_ADDRESS);
    CHECK(!page_tables_lookup(&tables, UINT64_MAX, &mapping));
}

static void test_large_mappings_cover_their_whole_span(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct page_tables tables;
    struct page_mapping mapping;
    uint64_t physical = 0x80000000ull;

    CHECK(page_tables_create(&tables, pool, FRAME_FOR_SUPERVISOR) == PAGE_OK);
    CHECK(page_tables_map_large(&tables, SHARED_ADDRESS + PAGE_BYTES, physical, READ_WRITE) ==
          PAGE_BAD_ADDRESS);
    CHECK(page_tables_map_large(&tables, SHARED_ADDRESS, physical, READ_WRITE) == PAGE_OK);
    CHECK(page_tables_lookup(&tables, SHARED_ADDRESS + PAGE_LARGE_BYTES - 1u, &mapping));
    CHECK(mapping.physical == physical + PAGE_LARGE_BYTES - 1u);
    CHECK(mapping.bytes == PAGE_LARGE_BYTES);
    CHECK(page_tables_map(&tables, SHARED_ADDRESS + PAGE_BYTES, physical, PAGE_READ) ==
          PAGE_ALREADY_MAPPED);
    CHECK(page_tables_map_large(&tables, SHARED_ADDRESS, physical, PAGE_READ) ==
          PAGE_ALREADY_MAPPED);
    CHECK(page_tables_unmap(&tables, SHARED_ADDRESS, &mapping) == PAGE_BAD_ADDRESS);
}

static void test_fresh_pages_are_zeroed_owned_and_returned(void)
{
    struct frame_pool *pool = frame_arena_open();
    uint64_t free_before = pool->free_frames;
    struct address_space space = open_space(pool);
    struct page_mapping mapping;
    uint8_t content[2u * PAGE_BYTES];

    memset(content, 0xff, sizeof(content));
    CHECK(address_space_map_fresh(&space, USER_BASE, 2u * PAGE_BYTES, READ_WRITE) == PAGE_OK);
    CHECK(page_tables_lookup(&space.tables, USER_BASE, &mapping));
    CHECK((mapping.flags & (PAGE_USER | PAGE_OWNED)) == (PAGE_USER | PAGE_OWNED));
    CHECK(user_memory_read(&space, USER_BASE, content, sizeof(content)));
    for (size_t index = 0; index < sizeof(content); index++) {
        if (content[index] != 0) {
            CHECK(content[index] == 0);
            break;
        }
    }
    CHECK(space.owned_frames == 2);
    CHECK(address_space_frames(&space) == 2 + space.tables.table_frames);
    CHECK(pool->free_frames == free_before - address_space_frames(&space));
    address_space_unmap(&space, USER_BASE, PAGE_BYTES);
    CHECK(space.owned_frames == 1);
    address_space_destroy(&space);
    CHECK(pool->free_frames == free_before);
}

static void test_failed_mapping_leaves_no_frame_behind(void)
{
    struct frame_pool *pool = frame_arena_open();
    uint64_t free_before = pool->free_frames;
    bool mapped = false;

    for (uint64_t budget = 0; budget < 32 && !mapped; budget++) {
        struct address_space space;
        enum page_status status;

        pool->allocations_before_failure = budget;
        status = address_space_create(&space, pool, NULL, user_region);
        if (status == PAGE_OK) {
            status = address_space_map_fresh(&space, USER_BASE, 8u * PAGE_BYTES, READ_WRITE);
        }
        if (status == PAGE_OK) {
            mapped = true;
        } else {
            CHECK(status == PAGE_OUT_OF_MEMORY);
            CHECK(space.owned_frames == 0);
        }
        pool->allocations_before_failure = FRAME_UNLIMITED_ALLOCATIONS;
        address_space_destroy(&space);
        CHECK(pool->free_frames == free_before);
    }
    CHECK(mapped);
}

static void test_borrowed_frames_survive_the_space(void)
{
    struct frame_pool *pool = frame_arena_open();
    uint64_t frame = supervisor_frame(pool);
    uint64_t free_before = pool->free_frames;
    struct address_space space = open_space(pool);
    struct page_mapping mapping;

    CHECK(address_space_map_borrowed(&space, USER_BASE, frame, PAGE_BYTES, PAGE_READ) == PAGE_OK);
    CHECK(page_tables_lookup(&space.tables, USER_BASE, &mapping));
    CHECK((mapping.flags & PAGE_OWNED) == 0);
    CHECK(space.owned_frames == 0);
    address_space_destroy(&space);
    CHECK(pool->free_frames == free_before);
    CHECK(frame_pool_free(pool, frame, 0) == FRAME_OK);
}

static void test_regions_outside_the_user_range_are_refused(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct address_space space = open_space(pool);
    struct address_space misplaced;

    CHECK(address_space_map_fresh(&space, USER_BASE - PAGE_BYTES, PAGE_BYTES, READ_WRITE) ==
          PAGE_BAD_ADDRESS);
    CHECK(address_space_map_fresh(&space, USER_BASE + USER_BYTES, PAGE_BYTES, READ_WRITE) ==
          PAGE_BAD_ADDRESS);
    CHECK(address_space_map_fresh(&space, USER_BASE + USER_BYTES - PAGE_BYTES, 2u * PAGE_BYTES,
                                  READ_WRITE) == PAGE_BAD_ADDRESS);
    CHECK(address_space_map_fresh(&space, USER_BASE + 1u, PAGE_BYTES, READ_WRITE) ==
          PAGE_BAD_ADDRESS);
    CHECK(address_space_map_fresh(&space, USER_BASE, 0, READ_WRITE) == PAGE_BAD_ADDRESS);
    CHECK(address_space_map_fresh(&space, USER_BASE, PAGE_BYTES, READ_WRITE | PAGE_USER) ==
          PAGE_BAD_ADDRESS);
    CHECK(address_space_map_fresh(&space, USER_BASE, PAGE_BYTES, READ_WRITE | PAGE_EXECUTE) ==
          PAGE_BAD_PERMISSIONS);
    CHECK(space.owned_frames == 0);
    CHECK(address_space_create(&misplaced, pool, NULL,
                               (struct memory_range){USER_BASE + PAGE_BYTES, USER_BYTES}) ==
          PAGE_BAD_ADDRESS);
    CHECK(address_space_create(&misplaced, pool, NULL,
                               (struct memory_range){USER_BASE, PAGE_ROOT_SPAN + PAGE_BYTES}) ==
          PAGE_BAD_ADDRESS);
    CHECK(!address_space_region_is_valid((struct memory_range){USER_BASE, 0}));
}

static void test_copies_cross_pages_and_respect_permissions(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct address_space space = open_space(pool);
    uint64_t boundary = USER_BASE + PAGE_BYTES;
    uint8_t written[16];
    uint8_t read[16] = {0};

    for (uint8_t index = 0; index < sizeof(written); index++) {
        written[index] = (uint8_t)(index + 1u);
    }
    CHECK(address_space_map_fresh(&space, USER_BASE, 2u * PAGE_BYTES, READ_WRITE) == PAGE_OK);
    CHECK(address_space_map_fresh(&space, USER_BASE + 2u * PAGE_BYTES, PAGE_BYTES, PAGE_READ) ==
          PAGE_OK);
    CHECK(user_memory_write(&space, boundary - 8u, written, sizeof(written)));
    CHECK(user_memory_read(&space, boundary - 8u, read, sizeof(read)));
    CHECK(memcmp(read, written, sizeof(written)) == 0);

    memset(read, 0, sizeof(read));
    CHECK(!user_memory_write(&space, USER_BASE + 2u * PAGE_BYTES - 8u, written, sizeof(written)));
    CHECK(user_memory_read(&space, USER_BASE + 2u * PAGE_BYTES - 8u, read, 8));
    CHECK(memcmp(read, "\0\0\0\0\0\0\0\0", 8) == 0);
    CHECK(user_memory_read(&space, USER_BASE + 2u * PAGE_BYTES - 8u, read, sizeof(read)));
    CHECK(!user_memory_is_writable(&space, USER_BASE + 2u * PAGE_BYTES, 1));
    CHECK(user_memory_is_readable(&space, USER_BASE + 2u * PAGE_BYTES, PAGE_BYTES));
}

static void test_invalid_user_ranges_are_rejected_without_access(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct address_space space = open_space(pool);
    uint8_t bytes[32];
    uint8_t untouched[32];

    memset(bytes, 0x5a, sizeof(bytes));
    memset(untouched, 0x5a, sizeof(untouched));
    CHECK(address_space_map_fresh(&space, USER_BASE, PAGE_BYTES, READ_WRITE) == PAGE_OK);
    CHECK(address_space_map_fresh(&space, USER_BASE + 2u * PAGE_BYTES, PAGE_BYTES, READ_WRITE) ==
          PAGE_OK);

    CHECK(!user_memory_read(&space, 0, bytes, 8));
    CHECK(!user_memory_read(&space, USER_BASE + PAGE_BYTES - 8u, bytes, 16));
    CHECK(!user_memory_read(&space, USER_BASE + PAGE_BYTES, bytes, 1));
    CHECK(!user_memory_read(&space, USER_BASE - 4u, bytes, 8));
    CHECK(!user_memory_read(&space, UINT64_MAX - 3u, bytes, 8));
    CHECK(!user_memory_read(&space, USER_BASE, bytes, UINT64_MAX));
    CHECK(!user_memory_read(&space, USER_BASE + USER_BYTES - 4u, bytes, 8));
    CHECK(!user_memory_read(&space, USER_BASE + USER_BYTES, bytes, 1));
    CHECK(memcmp(bytes, untouched, sizeof(bytes)) == 0);

    CHECK(!user_memory_write(&space, USER_BASE + PAGE_BYTES - 8u, bytes, 16));
    CHECK(user_memory_read(&space, USER_BASE + PAGE_BYTES - 8u, bytes, 8));
    CHECK(memcmp(bytes, "\0\0\0\0\0\0\0\0", 8) == 0);
    CHECK(user_memory_read(&space, USER_BASE, bytes, 0));
    CHECK(user_memory_write(&space, USER_BASE + USER_BYTES, bytes, 0));
    CHECK(!user_memory_write(&space, USER_BASE + USER_BYTES + 1u, bytes, 0));
}

static void test_spaces_do_not_see_each_other(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct address_space first = open_space(pool);
    struct address_space second = open_space(pool);
    uint64_t value = 0;

    CHECK(address_space_map_fresh(&first, USER_BASE, PAGE_BYTES, READ_WRITE) == PAGE_OK);
    CHECK(address_space_map_fresh(&second, USER_BASE, PAGE_BYTES, READ_WRITE) == PAGE_OK);
    CHECK(address_space_map_fresh(&first, USER_BASE + PAGE_BYTES, PAGE_BYTES, READ_WRITE) ==
          PAGE_OK);
    CHECK(user_memory_write(&first, USER_BASE, &(uint64_t){0x1111111111111111ull}, 8));
    CHECK(user_memory_write(&second, USER_BASE, &(uint64_t){0x2222222222222222ull}, 8));
    CHECK(user_memory_read(&first, USER_BASE, &value, 8) && value == 0x1111111111111111ull);
    CHECK(user_memory_read(&second, USER_BASE, &value, 8) && value == 0x2222222222222222ull);
    CHECK(!user_memory_read(&second, USER_BASE + PAGE_BYTES, &value, 8));
    address_space_destroy(&first);
    CHECK(user_memory_read(&second, USER_BASE, &value, 8) && value == 0x2222222222222222ull);
}

static void test_shared_supervisor_roots_stay_private_to_the_supervisor(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct page_tables supervisor;
    struct address_space space;
    struct page_mapping mapping;
    uint64_t frame = supervisor_frame(pool);
    uint64_t free_before;
    uint64_t value = 0;

    CHECK(page_tables_create(&supervisor, pool, FRAME_FOR_SUPERVISOR) == PAGE_OK);
    CHECK(page_tables_map(&supervisor, SHARED_ADDRESS, frame, READ_WRITE) == PAGE_OK);
    CHECK(page_tables_root_is_used(&supervisor, SHARED_ROOT_INDEX));
    CHECK(!page_tables_root_is_used(&supervisor, 1));
    free_before = pool->free_frames;

    CHECK(address_space_create(&space, pool, &supervisor, user_region) == PAGE_OK);
    CHECK(page_tables_lookup(&space.tables, SHARED_ADDRESS, &mapping));
    CHECK(mapping.physical == frame && (mapping.flags & PAGE_USER) == 0);
    CHECK(!user_memory_read(&space, SHARED_ADDRESS, &value, 8));
    CHECK(!user_memory_write(&space, SHARED_ADDRESS, &value, 8));
    CHECK(address_space_map_fresh(&space, SHARED_ADDRESS + PAGE_BYTES, PAGE_BYTES, READ_WRITE) ==
          PAGE_BAD_ADDRESS);
    address_space_destroy(&space);
    CHECK(pool->free_frames == free_before);
    CHECK(page_tables_lookup(&supervisor, SHARED_ADDRESS, &mapping));
}

static void test_loader_fills_read_only_pages(void)
{
    struct frame_pool *pool = frame_arena_open();
    struct address_space space = open_space(pool);
    uint8_t code[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    uint8_t read[8] = {0};

    CHECK(address_space_map_fresh(&space, USER_BASE, PAGE_BYTES, READ_EXECUTE) == PAGE_OK);
    CHECK(!user_memory_write(&space, USER_BASE, code, sizeof(code)));
    CHECK(address_space_fill(&space, USER_BASE + 4u, code, sizeof(code)));
    CHECK(user_memory_read(&space, USER_BASE + 4u, read, sizeof(read)));
    CHECK(memcmp(read, code, sizeof(code)) == 0);
    CHECK(!address_space_fill(&space, USER_BASE + PAGE_BYTES - 4u, code, sizeof(code)));
}

int main(void)
{
    test_mappings_translate_and_can_be_removed();
    test_writable_pages_are_never_executable();
    test_addresses_must_be_aligned_and_canonical();
    test_large_mappings_cover_their_whole_span();
    test_fresh_pages_are_zeroed_owned_and_returned();
    test_failed_mapping_leaves_no_frame_behind();
    test_borrowed_frames_survive_the_space();
    test_regions_outside_the_user_range_are_refused();
    test_copies_cross_pages_and_respect_permissions();
    test_invalid_user_ranges_are_rejected_without_access();
    test_spaces_do_not_see_each_other();
    test_shared_supervisor_roots_stay_private_to_the_supervisor();
    test_loader_fills_read_only_pages();
    frame_arena_close();
    return check_finish("address-space");
}
