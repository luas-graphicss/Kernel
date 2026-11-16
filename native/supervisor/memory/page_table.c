#include "kernel/memory/page_table.h"

#include <stddef.h>

#include "kernel/memory/string.h"

#define ROOT_LEVEL 2u
#define LARGE_LEVEL 1u
#define SMALL_LEVEL 0u
#define INDEX_BITS 9u
#define INDEX_MASK 0x1ffull
#define ENTRY_FLAG_BITS 10u
#define ENTRY_FLAGS_MASK 0x3ffull
#define PHYSICAL_LIMIT (1ull << 56)
#define LEAF_PERMISSIONS (PAGE_READ | PAGE_WRITE | PAGE_EXECUTE)
#define CALLER_FLAGS (LEAF_PERMISSIONS | PAGE_USER | PAGE_GLOBAL | PAGE_OWNED)

static uint64_t *table_at(uint64_t physical)
{
    return (uint64_t *)(uintptr_t)physical;
}

static uint32_t entry_index(uint64_t address, uint32_t level)
{
    return (uint32_t)((address >> (FRAME_SHIFT + INDEX_BITS * level)) & INDEX_MASK);
}

static uint64_t level_span(uint32_t level)
{
    return PAGE_BYTES << (INDEX_BITS * level);
}

static uint64_t entry_target(uint64_t entry)
{
    return (entry >> ENTRY_FLAG_BITS) << FRAME_SHIFT;
}

static uint64_t make_entry(uint64_t physical, uint64_t flags)
{
    return ((physical >> FRAME_SHIFT) << ENTRY_FLAG_BITS) | flags;
}

static bool is_leaf(uint64_t entry)
{
    return (entry & LEAF_PERMISSIONS) != 0;
}

static bool flags_are_valid(uint64_t flags)
{
    if ((flags & ~CALLER_FLAGS) != 0 || (flags & (PAGE_READ | PAGE_EXECUTE)) == 0) {
        return false;
    }
    if ((flags & PAGE_WRITE) != 0 && (flags & (PAGE_EXECUTE | PAGE_READ)) != PAGE_READ) {
        return false;
    }
    return true;
}

static uint64_t leaf_entry(uint64_t physical, uint64_t flags)
{
    uint64_t state = PAGE_VALID | PAGE_ACCESSED;

    if ((flags & PAGE_WRITE) != 0) {
        state |= PAGE_DIRTY;
    }
    return make_entry(physical, flags | state);
}

static enum page_status allocate_table(struct page_tables *tables, uint64_t *physical)
{
    if (frame_pool_allocate(tables->pool, 0, tables->purpose, physical) != FRAME_OK) {
        return PAGE_OUT_OF_MEMORY;
    }
    memset(table_at(*physical), 0, (size_t)FRAME_BYTES);
    tables->table_frames++;
    return PAGE_OK;
}

static void free_table(struct page_tables *tables, uint64_t physical)
{
    frame_pool_free(tables->pool, physical, 0);
    tables->table_frames--;
}

static enum page_status descend(struct page_tables *tables, uint64_t address, uint32_t target,
                                bool create, uint64_t **slot)
{
    uint64_t *table = table_at(tables->root);

    for (uint32_t level = ROOT_LEVEL; level > target; level--) {
        uint64_t *entry = &table[entry_index(address, level)];

        if ((*entry & PAGE_VALID) == 0) {
            uint64_t child;
            enum page_status status;

            if (!create) {
                return PAGE_NOT_MAPPED;
            }
            status = allocate_table(tables, &child);
            if (status != PAGE_OK) {
                return status;
            }
            *entry = make_entry(child, PAGE_VALID);
        } else if (is_leaf(*entry)) {
            return PAGE_ALREADY_MAPPED;
        }
        table = table_at(entry_target(*entry));
    }
    *slot = &table[entry_index(address, target)];
    return PAGE_OK;
}

static enum page_status map_at(struct page_tables *tables, uint64_t address, uint64_t physical,
                               uint64_t flags, uint32_t level)
{
    uint64_t *slot = NULL;
    enum page_status status;

    if (address % level_span(level) != 0 || address >= PAGE_VIRTUAL_LIMIT ||
        physical % level_span(level) != 0 || physical >= PHYSICAL_LIMIT) {
        return PAGE_BAD_ADDRESS;
    }
    if (!flags_are_valid(flags)) {
        return PAGE_BAD_PERMISSIONS;
    }
    status = descend(tables, address, level, true, &slot);
    if (status != PAGE_OK) {
        return status;
    }
    if ((*slot & PAGE_VALID) != 0) {
        return PAGE_ALREADY_MAPPED;
    }
    *slot = leaf_entry(physical, flags);
    return PAGE_OK;
}

static void visit_leaf(uint64_t entry, uint32_t level, page_visitor visit, void *context)
{
    visit(context, (struct page_mapping){
                       .physical = entry_target(entry),
                       .flags = entry & ENTRY_FLAGS_MASK,
                       .bytes = level_span(level),
                   });
}

static void release_table(struct page_tables *tables, uint64_t physical, uint32_t level,
                          page_visitor visit, void *context)
{
    const uint64_t *table = table_at(physical);

    for (uint32_t index = 0; index < PAGE_TABLE_ENTRIES; index++) {
        uint64_t entry = table[index];

        if ((entry & PAGE_VALID) == 0) {
            continue;
        }
        if (is_leaf(entry)) {
            visit_leaf(entry, level, visit, context);
        } else if (level > SMALL_LEVEL) {
            release_table(tables, entry_target(entry), level - 1u, visit, context);
        }
    }
    free_table(tables, physical);
}

enum page_status page_tables_create(struct page_tables *tables, struct frame_pool *pool,
                                    enum frame_purpose purpose)
{
    *tables = (struct page_tables){.pool = pool, .purpose = purpose};
    return allocate_table(tables, &tables->root);
}

enum page_status page_tables_map(struct page_tables *tables, uint64_t address, uint64_t physical,
                                 uint64_t flags)
{
    return map_at(tables, address, physical, flags, SMALL_LEVEL);
}

enum page_status page_tables_map_large(struct page_tables *tables, uint64_t address,
                                       uint64_t physical, uint64_t flags)
{
    return map_at(tables, address, physical, flags, LARGE_LEVEL);
}

bool page_tables_lookup(const struct page_tables *tables, uint64_t address,
                        struct page_mapping *mapping)
{
    const uint64_t *table = table_at(tables->root);

    if (address >= PAGE_VIRTUAL_LIMIT) {
        return false;
    }
    for (uint32_t level = ROOT_LEVEL;; level--) {
        uint64_t entry = table[entry_index(address, level)];

        if ((entry & PAGE_VALID) == 0) {
            return false;
        }
        if (is_leaf(entry)) {
            *mapping = (struct page_mapping){
                .physical = entry_target(entry) + (address & (level_span(level) - 1u)),
                .flags = entry & ENTRY_FLAGS_MASK,
                .bytes = level_span(level),
            };
            return true;
        }
        if (level == SMALL_LEVEL) {
            return false;
        }
        table = table_at(entry_target(entry));
    }
}

enum page_status page_tables_unmap(struct page_tables *tables, uint64_t address,
                                   struct page_mapping *removed)
{
    uint64_t *slot = NULL;
    enum page_status status;

    if (address % PAGE_BYTES != 0 || address >= PAGE_VIRTUAL_LIMIT) {
        return PAGE_BAD_ADDRESS;
    }
    status = descend(tables, address, SMALL_LEVEL, false, &slot);
    if (status == PAGE_ALREADY_MAPPED) {
        return PAGE_BAD_ADDRESS;
    }
    if (status != PAGE_OK || (*slot & PAGE_VALID) == 0) {
        return PAGE_NOT_MAPPED;
    }
    *removed = (struct page_mapping){
        .physical = entry_target(*slot),
        .flags = *slot & ENTRY_FLAGS_MASK,
        .bytes = PAGE_BYTES,
    };
    *slot = 0;
    return PAGE_OK;
}

bool page_tables_root_is_used(const struct page_tables *tables, uint32_t root_index)
{
    return (table_at(tables->root)[root_index] & PAGE_VALID) != 0;
}

void page_tables_share_root(struct page_tables *tables, const struct page_tables *source,
                            uint32_t root_index)
{
    table_at(tables->root)[root_index] = table_at(source->root)[root_index];
}

void page_tables_release_root(struct page_tables *tables, uint32_t root_index, page_visitor visit,
                              void *context)
{
    uint64_t *slot = &table_at(tables->root)[root_index];
    uint64_t entry = *slot;

    *slot = 0;
    if ((entry & PAGE_VALID) == 0) {
        return;
    }
    if (is_leaf(entry)) {
        visit_leaf(entry, ROOT_LEVEL, visit, context);
        return;
    }
    release_table(tables, entry_target(entry), LARGE_LEVEL, visit, context);
}

void page_tables_destroy(struct page_tables *tables)
{
    if (tables->root != 0) {
        free_table(tables, tables->root);
        tables->root = 0;
    }
}
