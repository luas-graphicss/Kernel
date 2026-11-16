#include <stdint.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "probe/probe.h"
#include "process_calls.h"

#define SYSCALL_ARGUMENTS_MIN 1
#define SYSCALL_ARGUMENTS_MAX 7

static long argument(size_t count, const mp_obj_t *arguments, size_t index)
{
    return index < count ? (long)mp_obj_get_int_truncated(arguments[index]) : 0;
}

static mp_obj_t probe_syscall(size_t count, const mp_obj_t *arguments)
{
    return mp_obj_new_int(process_call(
        argument(count, arguments, 1), argument(count, arguments, 2), argument(count, arguments, 3),
        argument(count, arguments, 4), argument(count, arguments, 5), argument(count, arguments, 6),
        argument(count, arguments, 0)));
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(probe_syscall_obj, SYSCALL_ARGUMENTS_MIN,
                                    SYSCALL_ARGUMENTS_MAX, probe_syscall);

static mp_obj_t probe_spin(void)
{
    probe_pattern_spin();
}
MP_DEFINE_CONST_FUN_OBJ_0(probe_spin_obj, probe_spin);

static mp_obj_t probe_hold_registers(mp_obj_t seed, mp_obj_t rounds)
{
    return mp_obj_new_bool(probe_pattern_hold_registers((uint64_t)mp_obj_get_int_truncated(seed),
                                                        (uint64_t)mp_obj_get_int_truncated(rounds)));
}
MP_DEFINE_CONST_FUN_OBJ_2(probe_hold_registers_obj, probe_hold_registers);

static mp_obj_t probe_hold_floats(mp_obj_t seed, mp_obj_t rounds)
{
    return mp_obj_new_bool(probe_pattern_hold_floats((uint64_t)mp_obj_get_int_truncated(seed),
                                                     (uint64_t)mp_obj_get_int_truncated(rounds)));
}
MP_DEFINE_CONST_FUN_OBJ_2(probe_hold_floats_obj, probe_hold_floats);

static mp_obj_t probe_floats_are_clear(void)
{
    return mp_obj_new_bool(probe_pattern_floats_are_clear());
}
MP_DEFINE_CONST_FUN_OBJ_0(probe_floats_are_clear_obj, probe_floats_are_clear);
