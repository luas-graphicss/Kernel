#include "pinned_buffers.h"

#include <stdlib.h>

#include "kernel/memory/buffer_pins.h"

struct pinned_buffer {
    uint64_t physical;
    uint64_t bytes;
    uint32_t pins;
};

static struct pinned_buffer buffers[PINNED_BUFFERS_CAPACITY];
static uint32_t buffer_count;

void pinned_buffers_reset(void)
{
    buffer_count = 0;
}

uint32_t pinned_buffers_add(uint64_t physical, uint64_t bytes)
{
    if (buffer_count == PINNED_BUFFERS_CAPACITY) {
        abort();
    }
    buffers[buffer_count] = (struct pinned_buffer){.physical = physical, .bytes = bytes};
    return buffer_count++;
}

uint32_t pinned_buffers_pins(uint32_t buffer)
{
    return buffers[buffer].pins;
}

bool buffer_pin(uint32_t buffer, uint64_t offset, uint64_t length, uint64_t *physical)
{
    if (buffer >= buffer_count || length == 0 || offset > buffers[buffer].bytes ||
        length > buffers[buffer].bytes - offset) {
        return false;
    }
    buffers[buffer].pins++;
    *physical = buffers[buffer].physical + offset;
    return true;
}

void buffer_unpin(uint32_t buffer)
{
    if (buffer >= buffer_count || buffers[buffer].pins == 0) {
        abort();
    }
    buffers[buffer].pins--;
}

uint64_t buffer_pinned_count(void)
{
    uint64_t pinned = 0;

    for (uint32_t buffer = 0; buffer < buffer_count; buffer++) {
        if (buffers[buffer].pins != 0) {
            pinned++;
        }
    }
    return pinned;
}
