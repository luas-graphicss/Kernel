#include <stdint.h>

#include "check.h"
#include "kernel/abi/rights.h"
#include "kernel/objects/object_table.h"

#define CAPACITY 4u
#define SMALL_GENERATION_LIMIT 3u

static struct slot_record records[CAPACITY];
static struct kernel_object objects[CAPACITY];
static uint32_t disposals;
static uint64_t disposed_handle;
static struct kernel_object disposed_object;

static void record_disposal(void *context, uint64_t handle, struct kernel_object object)
{
    (void)context;
    disposals++;
    disposed_handle = handle;
    disposed_object = object;
}

static struct object_table fresh_table(void)
{
    struct object_table table;

    disposals = 0;
    object_table_init(&table, records, objects, CAPACITY, record_disposal, NULL);
    return table;
}

static void test_handles_follow_the_documented_format(void)
{
    struct slot_table table;
    uint32_t index = 99;

    slot_table_init(&table, records, CAPACITY, SLOT_MAX_GENERATION);
    CHECK(slot_table_allocate(&table) == ((1ull << SLOT_INDEX_BITS) | 0u));
    CHECK(slot_table_allocate(&table) == ((1ull << SLOT_INDEX_BITS) | 1u));
    CHECK(table.live == 2);
    CHECK(slot_table_resolve(&table, (1ull << SLOT_INDEX_BITS) | 1u, &index) && index == 1);
    CHECK(!slot_table_resolve(&table, 0, &index));
    CHECK(!slot_table_resolve(&table, 1, &index));
    CHECK(!slot_table_resolve(&table, (1ull << SLOT_INDEX_BITS) | 2u, &index));
    CHECK(!slot_table_resolve(&table, (1ull << SLOT_INDEX_BITS) | CAPACITY, &index));
    CHECK(!slot_table_resolve(&table, (2ull << SLOT_INDEX_BITS) | 1u, &index));
    CHECK(!slot_table_resolve(&table, (1ull << 56) | (1ull << SLOT_INDEX_BITS) | 1u, &index));
    CHECK(!slot_table_resolve(&table, UINT64_MAX, &index));
    CHECK(slot_table_handle_at(&table, 1) == ((1ull << SLOT_INDEX_BITS) | 1u));
    CHECK(slot_table_handle_at(&table, 2) == SLOT_INVALID_HANDLE);
    CHECK(slot_table_handle_at(&table, CAPACITY) == SLOT_INVALID_HANDLE);
}

static void test_released_slots_are_reused_last_in_first_out(void)
{
    struct slot_table table;
    uint64_t first;
    uint64_t second;
    uint32_t index;

    slot_table_init(&table, records, CAPACITY, SLOT_MAX_GENERATION);
    first = slot_table_allocate(&table);
    second = slot_table_allocate(&table);
    slot_table_allocate(&table);
    CHECK(slot_table_release(&table, first));
    CHECK(slot_table_release(&table, second));
    CHECK(!slot_table_release(&table, second));
    CHECK(!slot_table_resolve(&table, first, &index));
    CHECK(slot_table_allocate(&table) == ((2ull << SLOT_INDEX_BITS) | 1u));
    CHECK(slot_table_allocate(&table) == ((2ull << SLOT_INDEX_BITS) | 0u));
    CHECK(!slot_table_resolve(&table, first, &index));
    CHECK(!slot_table_resolve(&table, second, &index));
}

static void test_exhausted_generation_retires_the_slot(void)
{
    struct slot_table table;
    uint32_t allocations = 0;

    slot_table_init(&table, records, 1, SMALL_GENERATION_LIMIT);
    for (;;) {
        uint64_t handle = slot_table_allocate(&table);

        if (handle == SLOT_INVALID_HANDLE) {
            break;
        }
        allocations++;
        CHECK(handle >> SLOT_INDEX_BITS == allocations);
        CHECK(slot_table_release(&table, handle));
    }
    CHECK(allocations == SMALL_GENERATION_LIMIT);
    CHECK(table.retired == 1 && table.live == 0);
}

static void test_object_lives_until_its_last_reference(void)
{
    struct object_table table = fresh_table();
    uint64_t handle = object_create(&table, OBJECT_ENDPOINT, 3, 77);
    struct kernel_object *object = object_find(&table, handle);

    CHECK(handle != SLOT_INVALID_HANDLE && object != NULL);
    CHECK(object->kind == OBJECT_ENDPOINT && object->owner == 3 && object->payload == 77);
    CHECK(object->references == 1);
    CHECK(object_retain(&table, handle));
    CHECK(object_release(&table, handle));
    CHECK(disposals == 0 && object_find(&table, handle) != NULL);
    CHECK(object_release(&table, handle));
    CHECK(disposals == 1 && disposed_handle == handle);
    CHECK(disposed_object.kind == OBJECT_ENDPOINT && disposed_object.payload == 77);
    CHECK(object_find(&table, handle) == NULL);
    CHECK(!object_release(&table, handle));
    CHECK(!object_retain(&table, handle));
    CHECK(disposals == 1);
}

static void test_reused_slot_does_not_revive_the_old_handle(void)
{
    struct object_table table = fresh_table();
    uint64_t old = object_create(&table, OBJECT_BUFFER, OBJECT_NO_OWNER, 1);
    uint64_t current;

    CHECK(object_release(&table, old));
    current = object_create(&table, OBJECT_PROCESS, OBJECT_NO_OWNER, 2);
    CHECK((current & SLOT_INDEX_MASK) == (old & SLOT_INDEX_MASK));
    CHECK(current != old);
    CHECK(object_find(&table, old) == NULL);
    CHECK(object_find(&table, current)->kind == OBJECT_PROCESS);
}

static void test_full_table_refuses_creation_until_a_release(void)
{
    struct object_table table = fresh_table();
    uint64_t handles[CAPACITY];

    for (uint32_t index = 0; index < CAPACITY; index++) {
        handles[index] = object_create(&table, OBJECT_ENDPOINT, 0, index);
        CHECK(handles[index] != SLOT_INVALID_HANDLE);
    }
    CHECK(object_create(&table, OBJECT_ENDPOINT, 0, 9) == SLOT_INVALID_HANDLE);
    CHECK(table.slots.live == CAPACITY);
    CHECK(object_release(&table, handles[2]));
    CHECK(object_create(&table, OBJECT_ENDPOINT, 0, 9) != SLOT_INVALID_HANDLE);
}

int main(void)
{
    test_handles_follow_the_documented_format();
    test_released_slots_are_reused_last_in_first_out();
    test_exhausted_generation_retires_the_slot();
    test_object_lives_until_its_last_reference();
    test_reused_slot_does_not_revive_the_old_handle();
    test_full_table_refuses_creation_until_a_release();
    return check_finish("object-table");
}
