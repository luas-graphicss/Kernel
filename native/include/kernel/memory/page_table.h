#ifndef KERNEL_MEMORY_PAGE_TABLE_H
#define KERNEL_MEMORY_PAGE_TABLE_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/memory/frame_pool.h"

#define PAGE_BYTES FRAME_BYTES
#define PAGE_TABLE_ENTRIES 512u
#define PAGE_LARGE_BYTES (PAGE_BYTES * PAGE_TABLE_ENTRIES)
#define PAGE_ROOT_SPAN (PAGE_LARGE_BYTES * PAGE_TABLE_ENTRIES)
#define PAGE_VIRTUAL_LIMIT (1ull << 38)

#define PAGE_VALID 0x001ull
#define PAGE_READ 0x002ull
#define PAGE_WRITE 0x004ull
#define PAGE_EXECUTE 0x008ull
#define PAGE_USER 0x010ull
#define PAGE_GLOBAL 0x020ull
#define PAGE_ACCESSED 0x040ull
#define PAGE_DIRTY 0x080ull
#define PAGE_OWNED 0x100ull

enum page_status {
    PAGE_OK,
    PAGE_BAD_ADDRESS,
    PAGE_BAD_PERMISSIONS,
    PAGE_ALREADY_MAPPED,
    PAGE_NOT_MAPPED,
    PAGE_OUT_OF_MEMORY,
};

struct page_tables {
    struct frame_pool *pool;
    enum frame_purpose purpose;
    uint64_t root;
    uint64_t table_frames;
};

struct page_mapping {
    uint64_t physical;
    uint64_t flags;
    uint64_t bytes;
};

typedef void (*page_visitor)(void *context, struct page_mapping mapping);

enum page_status page_tables_create(struct page_tables *tables, struct frame_pool *pool,
                                    enum frame_purpose purpose);
enum page_status page_tables_map(struct page_tables *tables, uint64_t address, uint64_t physical,
                                 uint64_t flags);
enum page_status page_tables_map_large(struct page_tables *tables, uint64_t address,
                                       uint64_t physical, uint64_t flags);
bool page_tables_lookup(const struct page_tables *tables, uint64_t address,
                        struct page_mapping *mapping);
enum page_status page_tables_unmap(struct page_tables *tables, uint64_t address,
                                   struct page_mapping *removed);
bool page_tables_root_is_used(const struct page_tables *tables, uint32_t root_index);
void page_tables_share_root(struct page_tables *tables, const struct page_tables *source,
                            uint32_t root_index);
void page_tables_release_root(struct page_tables *tables, uint32_t root_index, page_visitor visit,
                              void *context);
void page_tables_destroy(struct page_tables *tables);

#endif
