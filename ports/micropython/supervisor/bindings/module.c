#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"

mp_obj_t supervisor_new_tuple_of_integers(const uint64_t *values, size_t count)
{
    mp_obj_tuple_t *tuple = MP_OBJ_TO_PTR(mp_obj_new_tuple(count, NULL));

    for (size_t index = 0; index < count; index++) {
        tuple->items[index] = mp_obj_new_int_from_ull(values[index]);
    }
    return MP_OBJ_FROM_PTR(tuple);
}

static const mp_rom_map_elem_t supervisor_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__supervisor)},
    {MP_ROM_QSTR(MP_QSTR_machine), MP_ROM_PTR(&supervisor_machine_obj)},
    {MP_ROM_QSTR(MP_QSTR_limits), MP_ROM_PTR(&supervisor_limits_obj)},
    {MP_ROM_QSTR(MP_QSTR_user_region), MP_ROM_PTR(&supervisor_user_region_obj)},
    {MP_ROM_QSTR(MP_QSTR_arguments), MP_ROM_PTR(&supervisor_arguments_obj)},
    {MP_ROM_QSTR(MP_QSTR_inspect_boot_module), MP_ROM_PTR(&supervisor_inspect_boot_module_obj)},
    {MP_ROM_QSTR(MP_QSTR_run_boot_module), MP_ROM_PTR(&supervisor_run_boot_module_obj)},
};
static MP_DEFINE_CONST_DICT(supervisor_globals, supervisor_globals_table);

const mp_obj_module_t supervisor_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&supervisor_globals,
};

MP_REGISTER_MODULE(MP_QSTR__supervisor, supervisor_module);
