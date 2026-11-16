#ifndef KERNEL_MEMORY_ADDRESS_SPACE_H
#define KERNEL_MEMORY_ADDRESS_SPACE_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/memory/page_table.h"
#include "kernel/memory/range.h"

struct address_space {
    struct page_tables tables;
    struct memory_range user;
    uint64_t owned_frames;
};

bool address_space_region_is_valid(struct memory_range user);
enum page_status address_space_create(struct address_space *space, struct frame_pool *pool,
                                      const struct page_tables *shared, struct memory_range user);
enum page_status address_space_map_fresh(struct address_space *space, uint64_t address,
                                         uint64_t bytes, uint64_t permissions);
enum page_status address_space_map_borrowed(struct address_space *space, uint64_t address,
                                            uint64_t physical, uint64_t bytes,
                                            uint64_t permissions);
void address_space_unmap(struct address_space *space, uint64_t address, uint64_t bytes);
void address_space_destroy(struct address_space *space);
uint64_t address_space_frames(const struct address_space *space);
bool address_space_fill(struct address_space *space, uint64_t address, const void *source,
                        uint64_t length);

bool user_memory_is_readable(const struct address_space *space, uint64_t address, uint64_t length);
bool user_memory_is_writable(const struct address_space *space, uint64_t address, uint64_t length);
bool user_memory_read(const struct address_space *space, uint64_t address, void *destination,
                      uint64_t length);
bool user_memory_write(const struct address_space *space, uint64_t address, const void *source,
                       uint64_t length);

#endif
