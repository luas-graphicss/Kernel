#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"
#include "kernel/abi/errors.h"
#include "kernel/abi/process.h"
#include "kernel/abi/rights.h"
#include "kernel/abi/syscalls.h"
#include "kernel/memory/endian.h"
#include "process_calls.h"

#define MAPPINGS 16u
#define DOUBLE_WORD_BYTES 8u

struct mapping {
    bool used;
    bool writable;
    uint8_t *base;
    size_t bytes;
};

static struct mapping mappings[MAPPINGS];

static struct mapping *mapping_of(mp_obj_t token)
{
    mp_int_t index = mp_obj_get_int(token);

    if (index < 0 || (mp_uint_t)index >= MAPPINGS || !mappings[index].used) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer is not mapped"));
    }
    return &mappings[index];
}

static uint8_t *range_of(const struct mapping *mapping, mp_obj_t offset, size_t length)
{
    mp_int_t start = mp_obj_get_int(offset);

    if (start < 0 || (size_t)start > mapping->bytes || length > mapping->bytes - (size_t)start) {
        mp_raise_ValueError(MP_ERROR_TEXT("range is outside the buffer"));
    }
    return mapping->base + start;
}

static mp_obj_t process_buffer_map_binding(mp_obj_t handle, mp_obj_t writable)
{
    uint8_t described[BUFFER_MAPPING_BYTES];
    bool writes = mp_obj_is_true(writable);
    long rights = writes ? RIGHT_READ | RIGHT_WRITE : RIGHT_READ;
    size_t slot = 0;
    long status;

    while (slot < MAPPINGS && mappings[slot].used) {
        slot++;
    }
    if (slot == MAPPINGS) {
        return binding_signed(-KERNEL_ERROR_LIMIT_EXCEEDED);
    }
    status = process_call(binding_argument(handle), rights, (long)described, 0, 0, 0,
                          SYSCALL_BUFFER_MAP);
    if (status < 0) {
        return binding_signed(status);
    }
    mappings[slot] = (struct mapping){
        .used = true,
        .writable = writes,
        .base = (uint8_t *)(uintptr_t)little_endian_read(described + BUFFER_MAPPING_ADDRESS,
                                                         DOUBLE_WORD_BYTES),
        .bytes = (size_t)little_endian_read(described + BUFFER_MAPPING_LENGTH, DOUBLE_WORD_BYTES),
    };
    return binding_signed((long)slot);
}
MP_DEFINE_CONST_FUN_OBJ_2(process_buffer_map_obj, process_buffer_map_binding);

static mp_obj_t process_buffer_unmap_binding(mp_obj_t token)
{
    struct mapping *mapping = mapping_of(token);
    long status = process_call((long)mapping->base, 0, 0, 0, 0, 0, SYSCALL_BUFFER_UNMAP);

    mapping->used = false;
    return binding_signed(status);
}
MP_DEFINE_CONST_FUN_OBJ_1(process_buffer_unmap_obj, process_buffer_unmap_binding);

static mp_obj_t process_buffer_size_binding(mp_obj_t token)
{
    return binding_unsigned(mapping_of(token)->bytes);
}
MP_DEFINE_CONST_FUN_OBJ_1(process_buffer_size_obj, process_buffer_size_binding);

static mp_obj_t process_buffer_read_binding(mp_obj_t token, mp_obj_t offset, mp_obj_t length)
{
    const struct mapping *mapping = mapping_of(token);
    mp_int_t bytes = mp_obj_get_int(length);

    if (bytes < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("range is outside the buffer"));
    }
    return mp_obj_new_bytes(range_of(mapping, offset, (size_t)bytes), (size_t)bytes);
}
MP_DEFINE_CONST_FUN_OBJ_3(process_buffer_read_obj, process_buffer_read_binding);

static mp_obj_t process_buffer_write_binding(mp_obj_t token, mp_obj_t offset, mp_obj_t data)
{
    const struct mapping *mapping = mapping_of(token);
    mp_buffer_info_t bytes;

    mp_get_buffer_raise(data, &bytes, MP_BUFFER_READ);
    if (!mapping->writable) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer is mapped read-only"));
    }
    memcpy(range_of(mapping, offset, bytes.len), bytes.buf, bytes.len);
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_3(process_buffer_write_obj, process_buffer_write_binding);
