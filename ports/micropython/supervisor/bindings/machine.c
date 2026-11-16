#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"
#include "kernel/diagnostics/counters.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/startup/environment.h"
#include "kernel/startup/profile.h"

static mp_obj_t supervisor_machine(void)
{
    const struct boot_environment *environment = boot_environment_current();
    const uint64_t values[] = {
        environment->hart,
        environment->layout.ram.base,
        environment->layout.ram.length,
    };

    return supervisor_new_tuple_of_integers(values, MP_ARRAY_SIZE(values));
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_machine_obj, supervisor_machine);

static mp_obj_t supervisor_limits(void)
{
    const struct boot_environment *environment = boot_environment_current();
    const struct resource_profile *profile = resource_profile_compiled();
    const uint64_t values[] = {
        profile->memory_bytes,
        profile->processes,
        environment->supervisor_heap.length,
        profile->process_heap_bytes,
        profile->capabilities_per_process,
        profile->ipc_pending_bytes_per_process,
        profile->ipc_pending_bytes_global,
    };

    return supervisor_new_tuple_of_integers(values, MP_ARRAY_SIZE(values));
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_limits_obj, supervisor_limits);

static mp_obj_t supervisor_user_region(void)
{
    const struct boot_environment *environment = boot_environment_current();
    const uint64_t values[] = {
        environment->user_region.base,
        environment->user_region.length,
    };

    return supervisor_new_tuple_of_integers(values, MP_ARRAY_SIZE(values));
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_user_region_obj, supervisor_user_region);

static mp_obj_t supervisor_arguments(void)
{
    const char *arguments = boot_environment_current()->description.arguments;

    if (arguments == NULL) {
        return MP_OBJ_NEW_QSTR(MP_QSTR_);
    }
    return mp_obj_new_str(arguments, strlen(arguments));
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_arguments_obj, supervisor_arguments);

static mp_obj_t supervisor_memory(void)
{
    const struct frame_pool *pool = physical_memory_pool();
    const uint64_t values[] = {
        FRAME_BYTES,
        pool->usable_frames,
        pool->free_frames,
        pool->reserve_frames,
    };

    return supervisor_new_tuple_of_integers(values, MP_ARRAY_SIZE(values));
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_memory_obj, supervisor_memory);

static mp_obj_t supervisor_counters(void)
{
    uint64_t values[COUNTERS];

    resource_counters_read(values);
    return supervisor_new_tuple_of_integers(values, COUNTERS);
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_counters_obj, supervisor_counters);
