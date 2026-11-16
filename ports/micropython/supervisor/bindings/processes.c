#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"
#include "kernel/processes/process.h"
#include "kernel/processes/program.h"
#include "kernel/processes/run.h"
#include "kernel/processes/spawn.h"
#include "kernel/processes/supervision.h"

#define SPAWN_ARGUMENTS 5

static struct spawn_quota quota_from(const mp_obj_t *values)
{
    return (struct spawn_quota){
        .memory_frames = supervisor_unsigned(values[0]),
        .capabilities = (uint32_t)supervisor_unsigned(values[1]),
        .ipc_pending_bytes = supervisor_unsigned(values[2]),
    };
}

static mp_obj_t supervisor_prepare_program(void)
{
    const char *status = program_prepare();

    return mp_obj_new_str(status, strlen(status));
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_prepare_program_obj, supervisor_prepare_program);

static mp_obj_t supervisor_footprint(mp_obj_t heap_bytes)
{
    return supervisor_new_unsigned(spawn_footprint_frames(supervisor_unsigned(heap_bytes)));
}
MP_DEFINE_CONST_FUN_OBJ_1(supervisor_footprint_obj, supervisor_footprint);

static mp_obj_t supervisor_spawn(size_t count, const mp_obj_t *arguments)
{
    size_t name_length;
    const char *name = mp_obj_str_get_data(arguments[0], &name_length);

    (void)count;
    return supervisor_new_signed(spawn_initial(name, (uint32_t)name_length,
                                                supervisor_unsigned(arguments[1]),
                                                quota_from(arguments + 2)));
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(supervisor_spawn_obj, SPAWN_ARGUMENTS, SPAWN_ARGUMENTS,
                                    supervisor_spawn);

static mp_obj_t supervisor_pending_spawn(void)
{
    uint64_t requester;
    const struct spawn_request *request = spawn_pending(&requester);

    if (request == NULL) {
        return mp_const_none;
    }
    mp_obj_t items[] = {
        supervisor_new_unsigned(requester),
        mp_obj_new_str(request->name, request->name_length),
        MP_OBJ_NEW_SMALL_INT(request->priority),
        supervisor_new_unsigned(request->heap_bytes),
        supervisor_new_unsigned(request->memory_bytes),
        MP_OBJ_NEW_SMALL_INT(request->grant_count),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_pending_spawn_obj, supervisor_pending_spawn);

static mp_obj_t supervisor_admit_spawn(mp_obj_t memory_frames, mp_obj_t capabilities,
                                       mp_obj_t ipc_pending_bytes)
{
    const mp_obj_t values[] = {memory_frames, capabilities, ipc_pending_bytes};

    return supervisor_new_signed(spawn_admit(quota_from(values)));
}
MP_DEFINE_CONST_FUN_OBJ_3(supervisor_admit_spawn_obj, supervisor_admit_spawn);

static mp_obj_t supervisor_reject_spawn(mp_obj_t error)
{
    spawn_reject(-(int64_t)mp_obj_get_int(error));
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(supervisor_reject_spawn_obj, supervisor_reject_spawn);

static mp_obj_t supervisor_run_binding(mp_obj_t handle, mp_obj_t quantum_nanoseconds)
{
    struct run_outcome outcome =
        supervisor_run(supervisor_unsigned(handle), supervisor_unsigned(quantum_nanoseconds));
    mp_obj_t items[] = {
        MP_OBJ_NEW_SMALL_INT(outcome.result),
        supervisor_new_unsigned(outcome.value),
        supervisor_new_unsigned(outcome.detail),
    };

    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_2(supervisor_run_obj, supervisor_run_binding);

static mp_obj_t supervisor_next_event(void)
{
    struct kernel_event event;

    if (!process_event_pop(&event)) {
        return mp_const_none;
    }
    mp_obj_t items[] = {
        MP_OBJ_NEW_SMALL_INT(event.kind),
        supervisor_new_unsigned(event.subject),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_next_event_obj, supervisor_next_event);

static mp_obj_t supervisor_events_overflowed(void)
{
    return mp_obj_new_bool(process_events_take_overflow());
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_events_overflowed_obj, supervisor_events_overflowed);

static mp_obj_t supervisor_idle_binding(void)
{
    return mp_obj_new_bool(supervisor_idle());
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_idle_obj, supervisor_idle_binding);

static mp_obj_t supervisor_kill(mp_obj_t handle)
{
    return supervisor_new_signed(supervision_kill(supervisor_unsigned(handle)));
}
MP_DEFINE_CONST_FUN_OBJ_1(supervisor_kill_obj, supervisor_kill);

static mp_obj_t supervisor_release(mp_obj_t handle)
{
    return supervisor_new_signed(supervision_release(supervisor_unsigned(handle)));
}
MP_DEFINE_CONST_FUN_OBJ_1(supervisor_release_obj, supervisor_release);

static mp_obj_t supervisor_process_state(mp_obj_t handle)
{
    return MP_OBJ_NEW_SMALL_INT(supervision_state(supervisor_unsigned(handle)));
}
MP_DEFINE_CONST_FUN_OBJ_1(supervisor_process_state_obj, supervisor_process_state);
