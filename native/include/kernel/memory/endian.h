#ifndef KERNEL_MEMORY_ENDIAN_H
#define KERNEL_MEMORY_ENDIAN_H

#include <stddef.h>
#include <stdint.h>

#define LITTLE_ENDIAN_BITS_PER_BYTE 8u

static inline uint64_t little_endian_read(const uint8_t *bytes, size_t width)
{
    uint64_t value = 0;

    for (size_t index = 0; index < width; index++) {
        value |= (uint64_t)bytes[index] << (index * LITTLE_ENDIAN_BITS_PER_BYTE);
    }
    return value;
}

static inline void little_endian_write(uint8_t *bytes, size_t width, uint64_t value)
{
    for (size_t index = 0; index < width; index++) {
        bytes[index] = (uint8_t)(value >> (index * LITTLE_ENDIAN_BITS_PER_BYTE));
    }
}

#endif
