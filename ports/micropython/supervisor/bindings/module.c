#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"

mp_obj_t supervisor_new_tuple_of_integers(const uint64_t *values, size_t count)
{
    mp_obj_tuple_t *tuple = MP_OBJ_TO_PTR(mp_obj_new_tuple(count, NULL));

    for (size_t index = 0; index < count; index++) {
        tuple->items[index] = supervisor_new_unsigned(values[index]);
    }
    return MP_OBJ_FROM_PTR(tuple);
}

uint64_t supervisor_unsigned(mp_obj_t value)
{
    return (uint64_t)mp_obj_get_int_truncated(value);
}

static const mp_rom_map_elem_t supervisor_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__supervisor)},
    {MP_ROM_QSTR(MP_QSTR_machine), MP_ROM_PTR(&supervisor_machine_obj)},
    {MP_ROM_QSTR(MP_QSTR_limits), MP_ROM_PTR(&supervisor_limits_obj)},
    {MP_ROM_QSTR(MP_QSTR_user_region), MP_ROM_PTR(&supervisor_user_region_obj)},
    {MP_ROM_QSTR(MP_QSTR_arguments), MP_ROM_PTR(&supervisor_arguments_obj)},
    {MP_ROM_QSTR(MP_QSTR_memory), MP_ROM_PTR(&supervisor_memory_obj)},
    {MP_ROM_QSTR(MP_QSTR_counters), MP_ROM_PTR(&supervisor_counters_obj)},
    {MP_ROM_QSTR(MP_QSTR_collections), MP_ROM_PTR(&supervisor_collections_obj)},
    {MP_ROM_QSTR(MP_QSTR_prepare_program), MP_ROM_PTR(&supervisor_prepare_program_obj)},
    {MP_ROM_QSTR(MP_QSTR_footprint), MP_ROM_PTR(&supervisor_footprint_obj)},
    {MP_ROM_QSTR(MP_QSTR_spawn), MP_ROM_PTR(&supervisor_spawn_obj)},
    {MP_ROM_QSTR(MP_QSTR_pending_spawn), MP_ROM_PTR(&supervisor_pending_spawn_obj)},
    {MP_ROM_QSTR(MP_QSTR_admit_spawn), MP_ROM_PTR(&supervisor_admit_spawn_obj)},
    {MP_ROM_QSTR(MP_QSTR_reject_spawn), MP_ROM_PTR(&supervisor_reject_spawn_obj)},
    {MP_ROM_QSTR(MP_QSTR_run), MP_ROM_PTR(&supervisor_run_obj)},
    {MP_ROM_QSTR(MP_QSTR_next_event), MP_ROM_PTR(&supervisor_next_event_obj)},
    {MP_ROM_QSTR(MP_QSTR_events_overflowed), MP_ROM_PTR(&supervisor_events_overflowed_obj)},
    {MP_ROM_QSTR(MP_QSTR_idle), MP_ROM_PTR(&supervisor_idle_obj)},
    {MP_ROM_QSTR(MP_QSTR_kill), MP_ROM_PTR(&supervisor_kill_obj)},
    {MP_ROM_QSTR(MP_QSTR_release), MP_ROM_PTR(&supervisor_release_obj)},
    {MP_ROM_QSTR(MP_QSTR_process_state), MP_ROM_PTR(&supervisor_process_state_obj)},
};
static MP_DEFINE_CONST_DICT(supervisor_globals, supervisor_globals_table);

const mp_obj_module_t supervisor_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&supervisor_globals,
};

MP_REGISTER_MODULE(MP_QSTR__supervisor, supervisor_module);
