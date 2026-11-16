#ifndef GUEST_USER_PROBE_H
#define GUEST_USER_PROBE_H

#include <stdint.h>

#include "py/obj.h"

MP_DECLARE_CONST_FUN_OBJ_1(probe_load_obj);
MP_DECLARE_CONST_FUN_OBJ_2(probe_store_obj);
MP_DECLARE_CONST_FUN_OBJ_1(probe_jump_obj);
MP_DECLARE_CONST_FUN_OBJ_1(probe_address_obj);
MP_DECLARE_CONST_FUN_OBJ_2(probe_count_nonzero_obj);
MP_DECLARE_CONST_FUN_OBJ_0(probe_layout_obj);
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(probe_syscall_obj);
MP_DECLARE_CONST_FUN_OBJ_0(probe_spin_obj);
MP_DECLARE_CONST_FUN_OBJ_2(probe_hold_registers_obj);
MP_DECLARE_CONST_FUN_OBJ_2(probe_hold_floats_obj);
MP_DECLARE_CONST_FUN_OBJ_0(probe_floats_are_clear_obj);

long probe_pattern_hold_registers(uint64_t seed, uint64_t rounds);
long probe_pattern_hold_floats(uint64_t seed, uint64_t rounds);
long probe_pattern_floats_are_clear(void);
_Noreturn void probe_pattern_spin(void);

#endif
