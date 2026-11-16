#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"

static const mp_rom_map_elem_t process_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__process)},
    {MP_ROM_QSTR(MP_QSTR_startup), MP_ROM_PTR(&process_startup_obj)},
    {MP_ROM_QSTR(MP_QSTR_call), MP_ROM_PTR(&process_call_obj)},
    {MP_ROM_QSTR(MP_QSTR_send), MP_ROM_PTR(&process_send_obj)},
    {MP_ROM_QSTR(MP_QSTR_receive), MP_ROM_PTR(&process_receive_obj)},
    {MP_ROM_QSTR(MP_QSTR_request), MP_ROM_PTR(&process_request_obj)},
    {MP_ROM_QSTR(MP_QSTR_reply), MP_ROM_PTR(&process_reply_obj)},
    {MP_ROM_QSTR(MP_QSTR_spawn), MP_ROM_PTR(&process_spawn_obj)},
    {MP_ROM_QSTR(MP_QSTR_counters), MP_ROM_PTR(&process_counters_obj)},
    {MP_ROM_QSTR(MP_QSTR_buffer_map), MP_ROM_PTR(&process_buffer_map_obj)},
    {MP_ROM_QSTR(MP_QSTR_buffer_unmap), MP_ROM_PTR(&process_buffer_unmap_obj)},
    {MP_ROM_QSTR(MP_QSTR_buffer_size), MP_ROM_PTR(&process_buffer_size_obj)},
    {MP_ROM_QSTR(MP_QSTR_buffer_read), MP_ROM_PTR(&process_buffer_read_obj)},
    {MP_ROM_QSTR(MP_QSTR_buffer_write), MP_ROM_PTR(&process_buffer_write_obj)},
};
static MP_DEFINE_CONST_DICT(process_globals, process_globals_table);

const mp_obj_module_t process_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&process_globals,
};

MP_REGISTER_MODULE(MP_QSTR__process, process_module);
