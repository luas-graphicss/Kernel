#include <stdint.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "probe/probe.h"
#include "startup.h"

static const char read_only_marker[] = "probe";

static uintptr_t address_of(mp_obj_t value)
{
    return (uintptr_t)mp_obj_get_int_truncated(value);
}

static mp_obj_t probe_load(mp_obj_t address)
{
    const volatile uint64_t *location = (const volatile uint64_t *)address_of(address);

    return mp_obj_new_int_from_uint(*location);
}
MP_DEFINE_CONST_FUN_OBJ_1(probe_load_obj, probe_load);

static mp_obj_t probe_store(mp_obj_t address, mp_obj_t value)
{
    volatile uint64_t *location = (volatile uint64_t *)address_of(address);

    *location = (uint64_t)mp_obj_get_int_truncated(value);
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_2(probe_store_obj, probe_store);

static mp_obj_t probe_jump(mp_obj_t address)
{
    void (*target)(void) = (void (*)(void))address_of(address);

    target();
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(probe_jump_obj, probe_jump);

static mp_obj_t probe_address(mp_obj_t buffer)
{
    mp_buffer_info_t bytes;

    mp_get_buffer_raise(buffer, &bytes, MP_BUFFER_READ);
    return mp_obj_new_int_from_uint((uintptr_t)bytes.buf);
}
MP_DEFINE_CONST_FUN_OBJ_1(probe_address_obj, probe_address);

static mp_obj_t probe_count_nonzero(mp_obj_t address, mp_obj_t length)
{
    const volatile uint8_t *bytes = (const volatile uint8_t *)address_of(address);
    size_t total = (size_t)mp_obj_get_int_truncated(length);
    size_t nonzero = 0;

    for (size_t index = 0; index < total; index++) {
        if (bytes[index] != 0) {
            nonzero++;
        }
    }
    return mp_obj_new_int_from_uint(nonzero);
}
MP_DEFINE_CONST_FUN_OBJ_2(probe_count_nonzero_obj, probe_count_nonzero);

static mp_obj_t probe_layout(void)
{
    const struct process_startup *startup = process_startup();
    mp_obj_t items[] = {
        mp_obj_new_int_from_uint((uintptr_t)startup->heap_start),
        mp_obj_new_int_from_uint((uintptr_t)startup->heap_end),
        mp_obj_new_int_from_uint((uintptr_t)startup->stack_bottom),
        mp_obj_new_int_from_uint((uintptr_t)startup->stack_top),
        mp_obj_new_int_from_uint((uintptr_t)&probe_layout),
        mp_obj_new_int_from_uint((uintptr_t)read_only_marker),
    };

    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_0(probe_layout_obj, probe_layout);
