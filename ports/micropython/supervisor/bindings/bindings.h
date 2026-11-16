#ifndef KERNEL_PORT_SUPERVISOR_BINDINGS_H
#define KERNEL_PORT_SUPERVISOR_BINDINGS_H

#include "py/obj.h"

MP_DECLARE_CONST_FUN_OBJ_0(supervisor_machine_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_limits_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_user_region_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_arguments_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_inspect_boot_module_obj);
MP_DECLARE_CONST_FUN_OBJ_0(supervisor_run_boot_module_obj);

mp_obj_t supervisor_new_tuple_of_integers(const uint64_t *values, size_t count);

#endif
