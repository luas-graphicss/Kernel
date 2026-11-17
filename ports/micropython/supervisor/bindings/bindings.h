#ifndef KERNEL_PORT_SUPERVISOR_BINDINGS_H
#define KERNEL_PORT_SUPERVISOR_BINDINGS_H

#include "py/obj.h"

MP_DECLARE_CONST_FUN_OBJ_0(supervisor_machine_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_limits_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_user_region_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_arguments_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_memory_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_counters_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_collections_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_prepare_program_obj);
MP_DECLARE_CONST_FUN_OBJ_1(supervisor_footprint_obj);
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(supervisor_spawn_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_pending_spawn_obj);
MP_DECLARE_CONST_FUN_OBJ_3(supervisor_admit_spawn_obj);
MP_DECLARE_CONST_FUN_OBJ_1(supervisor_reject_spawn_obj);
MP_DECLARE_CONST_FUN_OBJ_2(supervisor_run_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_next_event_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_events_overflowed_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_idle_obj);
MP_DECLARE_CONST_FUN_OBJ_1(supervisor_kill_obj);
MP_DECLARE_CONST_FUN_OBJ_1(supervisor_release_obj);
MP_DECLARE_CONST_FUN_OBJ_1(supervisor_process_state_obj);

mp_obj_t supervisor_new_tuple_of_integers(const uint64_t *values, size_t count);
uint64_t supervisor_unsigned(mp_obj_t value);

static inline mp_obj_t supervisor_new_unsigned(uint64_t value)
{
    return mp_obj_new_int_from_uint((mp_uint_t)value);
}

static inline mp_obj_t supervisor_new_signed(int64_t value)
{
    return mp_obj_new_int((mp_int_t)value);
}

#endif
