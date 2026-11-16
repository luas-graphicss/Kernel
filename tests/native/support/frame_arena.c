#include "frame_arena.h"

#include <stdlib.h>
#include <string.h>

#define DIRTY_BYTE 0xa5

static struct frame_record records[FRAME_ARENA_FRAMES];
static struct frame_pool pool;
static void *memory;

struct frame_pool *frame_arena_open(void)
{
    size_t bytes = (size_t)FRAME_ARENA_FRAMES * (size_t)FRAME_BYTES;

    frame_arena_close();
    memory = aligned_alloc((size_t)FRAME_BYTES, bytes);
    if (memory == NULL) {
        abort();
    }
    memset(memory, DIRTY_BYTE, bytes);
    if (!frame_pool_init(&pool, (uint64_t)(uintptr_t)memory, records, FRAME_ARENA_FRAMES) ||
        frame_pool_add_usable(&pool, (struct memory_range){pool.base, bytes}) != FRAME_OK) {
        abort();
    }
    return &pool;
}

void frame_arena_close(void)
{
    free(memory);
    memory = NULL;
}
