#include <stdint.h>
#include <string.h>

#include "check.h"
#include "kernel/memory/layout.h"
#include "kernel/memory/range.h"

#define RAM_BASE 0x80000000ull
#define RAM_BYTES 0x10000000ull

static struct memory_range range(uint64_t base, uint64_t length)
{
    return (struct memory_range){.base = base, .length = length};
}

static void test_range_end_detects_overflow(void)
{
    uint64_t end = 0;

    CHECK(memory_range_end(range(0x1000, 0x2000), &end) && end == 0x3000);
    CHECK(memory_range_end(range(UINT64_MAX - 1u, 1), &end) && end == UINT64_MAX);
    CHECK(!memory_range_end(range(UINT64_MAX, 1), &end));
    CHECK(!memory_range_end(range(2, UINT64_MAX), &end));
}

static void test_containment(void)
{
    struct memory_range outer = range(0x1000, 0x1000);

    CHECK(memory_range_contains(outer, outer));
    CHECK(memory_range_contains(outer, range(0x1800, 0x100)));
    CHECK(!memory_range_contains(outer, range(0x1800, 0)));
    CHECK(!memory_range_contains(outer, range(0xfff, 2)));
    CHECK(!memory_range_contains(outer, range(0x1fff, 2)));
    CHECK(!memory_range_contains(outer, range(0x1800, UINT64_MAX)));
}

static void test_overlap(void)
{
    struct memory_range first = range(0x1000, 0x1000);

    CHECK(memory_ranges_overlap(first, range(0x1fff, 1)));
    CHECK(memory_ranges_overlap(first, range(0x0800, 0x801)));
    CHECK(!memory_ranges_overlap(first, range(0x2000, 0x1000)));
    CHECK(!memory_ranges_overlap(first, range(0x0800, 0x800)));
    CHECK(memory_ranges_overlap(first, range(0x4000, UINT64_MAX)));
}

static void test_layout_requires_enough_ram(void)
{
    struct memory_layout layout;

    CHECK(memory_layout_begin(&layout, range(RAM_BASE, RAM_BYTES), RAM_BYTES) == MEMORY_LAYOUT_OK);
    CHECK(memory_layout_begin(&layout, range(RAM_BASE, RAM_BYTES - 1u), RAM_BYTES) ==
          MEMORY_LAYOUT_INSUFFICIENT_RAM);
    CHECK(memory_layout_begin(&layout, range(UINT64_MAX, 2), 1) == MEMORY_LAYOUT_ADDRESS_OVERFLOW);
}

static void test_reservations_cannot_overlap_or_leave_ram(void)
{
    struct memory_layout layout;

    memory_layout_begin(&layout, range(RAM_BASE, RAM_BYTES), RAM_BYTES);
    CHECK(memory_layout_reserve(&layout, "kernel", range(RAM_BASE + 0x200000, 0x3000)) ==
          MEMORY_LAYOUT_OK);
    CHECK(memory_layout_reserve(&layout, "stack", range(RAM_BASE + 0x203000, 0x1000)) ==
          MEMORY_LAYOUT_OK);

    CHECK(memory_layout_reserve(&layout, "heap", range(RAM_BASE + 0x202fff, 0x10)) ==
          MEMORY_LAYOUT_OVERLAP);
    CHECK(layout.conflict != NULL && strcmp(layout.conflict, "kernel") == 0);
    CHECK(memory_layout_reserve(&layout, "empty", range(RAM_BASE, 0)) ==
          MEMORY_LAYOUT_EMPTY_REGION);
    CHECK(memory_layout_reserve(&layout, "wrapped", range(UINT64_MAX, 2)) ==
          MEMORY_LAYOUT_ADDRESS_OVERFLOW);
    CHECK(memory_layout_reserve(&layout, "below", range(RAM_BASE - 1u, 2)) ==
          MEMORY_LAYOUT_OUTSIDE_RAM);
    CHECK(memory_layout_reserve(&layout, "above", range(RAM_BASE + RAM_BYTES - 1u, 2)) ==
          MEMORY_LAYOUT_OUTSIDE_RAM);
    CHECK(layout.region_count == 2);
}

static void test_layout_has_a_fixed_capacity(void)
{
    struct memory_layout layout;

    memory_layout_begin(&layout, range(RAM_BASE, RAM_BYTES), RAM_BYTES);
    for (uint64_t index = 0; index < MEMORY_LAYOUT_MAX_REGIONS; index++) {
        CHECK(memory_layout_reserve(&layout, "page", range(RAM_BASE + index * 0x1000, 0x1000)) ==
              MEMORY_LAYOUT_OK);
    }
    CHECK(memory_layout_reserve(&layout, "page", range(RAM_BASE + 0x100000, 0x1000)) ==
          MEMORY_LAYOUT_TOO_MANY_REGIONS);
}

int main(void)
{
    test_range_end_detects_overflow();
    test_containment();
    test_overlap();
    test_layout_requires_enough_ram();
    test_reservations_cannot_overlap_or_leave_ram();
    test_layout_has_a_fixed_capacity();
    return check_finish("memory-layout");
}
