#include "kernel/memory/kernel_space.h"

#include <stdbool.h>
#include <stddef.h>

#include "kernel/arch/cpu.h"
#include "kernel/devices/uart_ns16550.h"
#include "kernel/diagnostics/halt.h"
#include "kernel/memory/image.h"
#include "kernel/memory/physical_memory.h"

#define NO_ACCESS 0ull
#define READ_WRITE (PAGE_READ | PAGE_WRITE)
#define READ_EXECUTE (PAGE_READ | PAGE_EXECUTE)

static struct page_tables tables;

static uint64_t symbol(const char *address)
{
    return (uint64_t)(uintptr_t)address;
}

static uint64_t align_down(uint64_t value, uint64_t alignment)
{
    return value - value % alignment;
}

static bool overlaps_firmware(const struct boot_environment *environment, uint64_t base,
                              uint64_t length)
{
    struct memory_range range = {.base = base, .length = length};
    const struct boot_description *description = &environment->description;

    for (size_t index = 0; index < description->reserved_count; index++) {
        if (memory_ranges_overlap(description->reserved[index], range)) {
            return true;
        }
    }
    return false;
}

static uint64_t page_permissions(const struct boot_environment *environment, uint64_t page)
{
    if (page == symbol(supervisor_stack_guard) ||
        overlaps_firmware(environment, page, PAGE_BYTES)) {
        return NO_ACCESS;
    }
    if (page >= symbol(kernel_image_start) && page < symbol(kernel_rodata_start)) {
        return READ_EXECUTE;
    }
    if (page >= symbol(kernel_rodata_start) && page < symbol(kernel_data_start)) {
        return PAGE_READ;
    }
    return READ_WRITE;
}

static bool span_needs_small_pages(const struct boot_environment *environment, uint64_t span)
{
    uint64_t end = span + PAGE_LARGE_BYTES;

    return overlaps_firmware(environment, span, PAGE_LARGE_BYTES) ||
           (span < symbol(kernel_data_start) && end > symbol(kernel_image_start)) ||
           (span <= symbol(supervisor_stack_guard) && end > symbol(supervisor_stack_guard));
}

static void require(enum page_status status)
{
    if (status != PAGE_OK) {
        kernel_panic("kernel-address-space");
    }
}

static void map_small_span(const struct boot_environment *environment, uint64_t span)
{
    for (uint64_t page = span; page < span + PAGE_LARGE_BYTES; page += PAGE_BYTES) {
        uint64_t permissions = page_permissions(environment, page);

        if (permissions != NO_ACCESS) {
            require(page_tables_map(&tables, page, page, permissions));
        }
    }
}

static void map_memory(const struct boot_environment *environment)
{
    struct memory_range ram = environment->layout.ram;
    uint64_t end = ram.base + ram.length;

    for (uint64_t span = align_down(ram.base, PAGE_LARGE_BYTES); span < end;
         span += PAGE_LARGE_BYTES) {
        if (span_needs_small_pages(environment, span)) {
            map_small_span(environment, span);
        } else {
            require(page_tables_map_large(&tables, span, span, READ_WRITE));
        }
    }
}

static void map_console(const struct boot_environment *environment)
{
    uint64_t base = align_down(environment->description.console.base, PAGE_BYTES);
    uint64_t end = environment->description.console.base + UART_NS16550_REGISTER_BYTES;

    for (uint64_t page = base; page < end; page += PAGE_BYTES) {
        require(page_tables_map(&tables, page, page, READ_WRITE));
    }
}

void kernel_space_init(const struct boot_environment *environment)
{
    struct memory_range user = environment->user_region;

    require(page_tables_create(&tables, physical_memory_pool(), FRAME_FOR_SUPERVISOR));
    map_memory(environment);
    map_console(environment);
    if (!address_space_region_is_valid(user) ||
        page_tables_root_is_used(&tables, (uint32_t)(user.base / PAGE_ROOT_SPAN))) {
        kernel_panic("user-region-overlaps-supervisor");
    }
    kernel_space_activate();
}

const struct page_tables *kernel_space_tables(void)
{
    return &tables;
}

void kernel_space_activate(void)
{
    mmu_activate(tables.root);
}

void address_space_activate(const struct address_space *space)
{
    mmu_activate(space->tables.root);
}
