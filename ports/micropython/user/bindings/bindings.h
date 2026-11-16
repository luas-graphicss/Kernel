#ifndef KERNEL_PORT_USER_BINDINGS_H
#define KERNEL_PORT_USER_BINDINGS_H

#include <stdint.h>

#include "py/obj.h"

MP_DECLARE_CONST_FUN_OBJ_0(process_startup_obj);
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(process_call_obj);
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(process_send_obj);
MP_DECLARE_CONST_FUN_OBJ_3(process_receive_obj);
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(process_request_obj);
MP_DECLARE_CONST_FUN_OBJ_3(process_reply_obj);
MP_DECLARE_CONST_FUN_OBJ_2(process_spawn_obj);
MP_DECLARE_CONST_FUN_OBJ_1(process_counters_obj);
MP_DECLARE_CONST_FUN_OBJ_2(process_buffer_map_obj);
MP_DECLARE_CONST_FUN_OBJ_1(process_buffer_unmap_obj);
MP_DECLARE_CONST_FUN_OBJ_1(process_buffer_size_obj);
MP_DECLARE_CONST_FUN_OBJ_3(process_buffer_read_obj);
MP_DECLARE_CONST_FUN_OBJ_3(process_buffer_write_obj);
MP_DECLARE_CONST_FUN_OBJ_1(process_device_list_obj);
MP_DECLARE_CONST_FUN_OBJ_2(process_device_open_obj);
MP_DECLARE_CONST_FUN_OBJ_3(process_device_config_obj);
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(process_device_submit_obj);
MP_DECLARE_CONST_FUN_OBJ_2(process_device_wait_obj);
MP_DECLARE_CONST_FUN_OBJ_2(process_serial_write_obj);
MP_DECLARE_CONST_FUN_OBJ_3(process_serial_read_obj);
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(process_crc32_obj);

static inline long binding_argument(mp_obj_t value)
{
    return (long)mp_obj_get_int_truncated(value);
}

static inline mp_obj_t binding_signed(long value)
{
    return mp_obj_new_int((mp_int_t)value);
}

static inline mp_obj_t binding_unsigned(uint64_t value)
{
    return mp_obj_new_int_from_uint((mp_uint_t)value);
}

#endif
