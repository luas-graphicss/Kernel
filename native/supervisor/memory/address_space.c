#include "kernel/memory/address_space.h"

#include <stddef.h>

#include "kernel/memory/string.h"

#define USER_PERMISSIONS (PAGE_READ | PAGE_WRITE | PAGE_EXECUTE)

static uint32_t user_root_index(const struct address_space *space)
{
    return (uint32_t)(space->user.base / PAGE_ROOT_SPAN);
}

static bool range_is_inside(const struct address_space *space, uint64_t address, uint64_t length)
{
    uint64_t offset;

    if (address < space->user.base) {
        return false;
    }
    offset = address - space->user.base;
    return offset <= space->user.length && length <= space->user.length - offset;
}

static bool pages_are_inside(const struct address_space *space, uint64_t address, uint64_t bytes)
{
    return bytes != 0 && address % PAGE_BYTES == 0 && bytes % PAGE_BYTES == 0 &&
           range_is_inside(space, address, bytes);
}

static void release_owned(void *context, struct page_mapping mapping)
{
    struct address_space *space = context;

    if ((mapping.flags & PAGE_OWNED) != 0) {
        frame_pool_free(space->tables.pool, mapping.physical, 0);
        space->owned_frames--;
    }
}

static bool range_has_flags(const struct address_space *space, uint64_t address, uint64_t length,
                            uint64_t required)
{
    if (!range_is_inside(space, address, length)) {
        return false;
    }
    while (length > 0) {
        struct page_mapping mapping;
        uint64_t room = PAGE_BYTES - address % PAGE_BYTES;
        uint64_t chunk = length < room ? length : room;

        if (!page_tables_lookup(&space->tables, address, &mapping) ||
            (mapping.flags & required) != required) {
            return false;
        }
        address += chunk;
        length -= chunk;
    }
    return true;
}

static void copy_pages(const struct address_space *space, uint64_t address, uint8_t *kernel,
                       uint64_t length, bool to_user)
{
    while (length > 0) {
        struct page_mapping mapping;
        uint64_t room = PAGE_BYTES - address % PAGE_BYTES;
        uint64_t chunk = length < room ? length : room;
        uint8_t *user;

        if (!page_tables_lookup(&space->tables, address, &mapping)) {
            return;
        }
        user = (uint8_t *)(uintptr_t)mapping.physical;
        if (to_user) {
            memcpy(user, kernel, (size_t)chunk);
        } else {
            memcpy(kernel, user, (size_t)chunk);
        }
        address += chunk;
        kernel += chunk;
        length -= chunk;
    }
}

bool address_space_region_is_valid(struct memory_range user)
{
    return user.length != 0 && user.base % PAGE_ROOT_SPAN == 0 && user.length % PAGE_BYTES == 0 &&
           user.length <= PAGE_ROOT_SPAN && user.base < PAGE_VIRTUAL_LIMIT;
}

enum page_status address_space_create(struct address_space *space, struct frame_pool *pool,
                                      const struct page_tables *shared, struct memory_range user)
{
    enum page_status status;

    if (!address_space_region_is_valid(user)) {
        return PAGE_BAD_ADDRESS;
    }
    *space = (struct address_space){.user = user};
    status = page_tables_create(&space->tables, pool, FRAME_FOR_PROCESS);
    if (status != PAGE_OK || shared == NULL) {
        return status;
    }
    for (uint32_t index = 0; index < PAGE_TABLE_ENTRIES; index++) {
        if (index != user_root_index(space)) {
            page_tables_share_root(&space->tables, shared, index);
        }
    }
    return PAGE_OK;
}

enum page_status address_space_map_fresh(struct address_space *space, uint64_t address,
                                         uint64_t bytes, uint64_t permissions)
{
    if (!pages_are_inside(space, address, bytes) || (permissions & ~USER_PERMISSIONS) != 0) {
        return PAGE_BAD_ADDRESS;
    }
    for (uint64_t offset = 0; offset < bytes; offset += PAGE_BYTES) {
        uint64_t frame;
        enum page_status status = PAGE_OUT_OF_MEMORY;

        if (frame_pool_allocate(space->tables.pool, 0, FRAME_FOR_PROCESS, &frame) == FRAME_OK) {
            memset((void *)(uintptr_t)frame, 0, (size_t)PAGE_BYTES);
            status = page_tables_map(&space->tables, address + offset, frame,
                                     permissions | PAGE_USER | PAGE_OWNED);
            if (status != PAGE_OK) {
                frame_pool_free(space->tables.pool, frame, 0);
            }
        }
        if (status != PAGE_OK) {
            address_space_unmap(space, address, offset);
            return status;
        }
        space->owned_frames++;
    }
    return PAGE_OK;
}

enum page_status address_space_map_borrowed(struct address_space *space, uint64_t address,
                                            uint64_t physical, uint64_t bytes, uint64_t permissions)
{
    if (!pages_are_inside(space, address, bytes) || (permissions & ~USER_PERMISSIONS) != 0) {
        return PAGE_BAD_ADDRESS;
    }
    for (uint64_t offset = 0; offset < bytes; offset += PAGE_BYTES) {
        enum page_status status = page_tables_map(&space->tables, address + offset,
                                                  physical + offset, permissions | PAGE_USER);

        if (status != PAGE_OK) {
            address_space_unmap(space, address, offset);
            return status;
        }
    }
    return PAGE_OK;
}

void address_space_unmap(struct address_space *space, uint64_t address, uint64_t bytes)
{
    for (uint64_t offset = 0; offset < bytes; offset += PAGE_BYTES) {
        struct page_mapping removed;

        if (page_tables_unmap(&space->tables, address + offset, &removed) == PAGE_OK) {
            release_owned(space, removed);
        }
    }
}

void address_space_destroy(struct address_space *space)
{
    if (space->tables.root == 0) {
        return;
    }
    page_tables_release_root(&space->tables, user_root_index(space), release_owned, space);
    page_tables_destroy(&space->tables);
}

uint64_t address_space_frames(const struct address_space *space)
{
    return space->owned_frames + space->tables.table_frames;
}

bool address_space_fill(struct address_space *space, uint64_t address, const void *source,
                        uint64_t length)
{
    if (!range_has_flags(space, address, length, PAGE_VALID | PAGE_USER)) {
        return false;
    }
    copy_pages(space, address, (uint8_t *)(uintptr_t)source, length, true);
    return true;
}

bool user_memory_is_readable(const struct address_space *space, uint64_t address, uint64_t length)
{
    return range_has_flags(space, address, length, PAGE_VALID | PAGE_USER | PAGE_READ);
}

bool user_memory_is_writable(const struct address_space *space, uint64_t address, uint64_t length)
{
    return range_has_flags(space, address, length, PAGE_VALID | PAGE_USER | PAGE_WRITE);
}

bool user_memory_read(const struct address_space *space, uint64_t address, void *destination,
                      uint64_t length)
{
    if (!user_memory_is_readable(space, address, length)) {
        return false;
    }
    copy_pages(space, address, destination, length, false);
    return true;
}

bool user_memory_write(const struct address_space *space, uint64_t address, const void *source,
                       uint64_t length)
{
    if (!user_memory_is_writable(space, address, length)) {
        return false;
    }
    copy_pages(space, address, (uint8_t *)(uintptr_t)source, length, true);
    return true;
}
