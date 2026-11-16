#ifndef TESTS_NATIVE_SUPPORT_FRAME_ARENA_H
#define TESTS_NATIVE_SUPPORT_FRAME_ARENA_H

#include <stdint.h>

#include "kernel/memory/frame_pool.h"

#define FRAME_ARENA_FRAMES 1024u

struct frame_pool *frame_arena_open(void);
void frame_arena_close(void);

#endif
