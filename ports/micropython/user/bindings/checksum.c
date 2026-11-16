#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"

#define NIBBLE_MASK 0xfu
#define NIBBLE_BITS 4u
#define CHECKSUM_ARGUMENTS_MIN 1
#define CHECKSUM_ARGUMENTS_MAX 2

static const uint32_t reflected_nibbles[] = {
    0x00000000u, 0x1db71064u, 0x3b6e20c8u, 0x26d930acu, 0x76dc4190u, 0x6b6b51f4u,
    0x4db26158u, 0x5005713cu, 0xedb88320u, 0xf00f9344u, 0xd6d6a3e8u, 0xcb61b38cu,
    0x9b64c2b0u, 0x86d3d2d4u, 0xa00ae278u, 0xbdbdf21cu,
};

static uint32_t crc32_extend(uint32_t checksum, const uint8_t *bytes, size_t length)
{
    uint32_t state = ~checksum;

    for (size_t index = 0; index < length; index++) {
        state ^= bytes[index];
        state = reflected_nibbles[state & NIBBLE_MASK] ^ (state >> NIBBLE_BITS);
        state = reflected_nibbles[state & NIBBLE_MASK] ^ (state >> NIBBLE_BITS);
    }
    return ~state;
}

static mp_obj_t process_crc32_binding(size_t count, const mp_obj_t *arguments)
{
    uint32_t checksum = count > 1 ? (uint32_t)mp_obj_get_int_truncated(arguments[1]) : 0;
    mp_buffer_info_t data;

    mp_get_buffer_raise(arguments[0], &data, MP_BUFFER_READ);
    return binding_unsigned(crc32_extend(checksum, data.buf, data.len));
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(process_crc32_obj, CHECKSUM_ARGUMENTS_MIN,
                                    CHECKSUM_ARGUMENTS_MAX, process_crc32_binding);
