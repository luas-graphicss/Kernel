#include "py/obj.h"
#include "py/runtime.h"

#include "probe/probe.h"

static const mp_rom_map_elem_t probe_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__probe)},
    {MP_ROM_QSTR(MP_QSTR_load), MP_ROM_PTR(&probe_load_obj)},
    {MP_ROM_QSTR(MP_QSTR_store), MP_ROM_PTR(&probe_store_obj)},
    {MP_ROM_QSTR(MP_QSTR_jump), MP_ROM_PTR(&probe_jump_obj)},
    {MP_ROM_QSTR(MP_QSTR_address), MP_ROM_PTR(&probe_address_obj)},
    {MP_ROM_QSTR(MP_QSTR_count_nonzero), MP_ROM_PTR(&probe_count_nonzero_obj)},
    {MP_ROM_QSTR(MP_QSTR_layout), MP_ROM_PTR(&probe_layout_obj)},
    {MP_ROM_QSTR(MP_QSTR_syscall), MP_ROM_PTR(&probe_syscall_obj)},
    {MP_ROM_QSTR(MP_QSTR_spin), MP_ROM_PTR(&probe_spin_obj)},
    {MP_ROM_QSTR(MP_QSTR_hold_registers), MP_ROM_PTR(&probe_hold_registers_obj)},
    {MP_ROM_QSTR(MP_QSTR_hold_floats), MP_ROM_PTR(&probe_hold_floats_obj)},
    {MP_ROM_QSTR(MP_QSTR_floats_are_clear), MP_ROM_PTR(&probe_floats_are_clear_obj)},
};
static MP_DEFINE_CONST_DICT(probe_globals, probe_globals_table);

const mp_obj_module_t probe_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&probe_globals,
};

MP_REGISTER_MODULE(MP_QSTR__probe, probe_module);
