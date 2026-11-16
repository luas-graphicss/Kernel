#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"
#include "kernel/abi/process.h"
#include "kernel/abi/syscalls.h"
#include "kernel/memory/endian.h"
#include "process_calls.h"
#include "startup.h"

#define SCALAR_ARGUMENTS_MIN 1
#define SCALAR_ARGUMENTS_MAX 3
#define DOUBLE_WORD_BYTES 8u

static bool takes_only_scalars(long number)
{
    switch (number) {
    case SYSCALL_CLOCK_NOW:
    case SYSCALL_PROCESS_YIELD:
    case SYSCALL_CAPABILITY_CLOSE:
    case SYSCALL_CAPABILITY_DERIVE:
    case SYSCALL_CAPABILITY_REVOKE:
    case SYSCALL_CAPABILITY_INSPECT:
    case SYSCALL_ENDPOINT_CREATE:
    case SYSCALL_BUFFER_CREATE:
    case SYSCALL_PROCESS_WAIT:
    case SYSCALL_PROCESS_KILL:
    case SYSCALL_PROCESS_INTERRUPT:
    case SYSCALL_DEVICE_CLAIM:
    case SYSCALL_DEVICE_RESET:
        return true;
    default:
        return false;
    }
}

static mp_obj_t process_startup_binding(void)
{
    const struct process_startup *startup = process_startup();
    mp_obj_tuple_t *handles = MP_OBJ_TO_PTR(mp_obj_new_tuple(startup->handle_count, NULL));

    for (size_t index = 0; index < startup->handle_count; index++) {
        handles->items[index] = binding_unsigned(startup->handles[index]);
    }
    mp_obj_t items[] = {
        mp_obj_new_str(startup->name, startup->name_length),
        mp_obj_new_bytes(startup->argument, startup->argument_length),
        MP_OBJ_FROM_PTR(handles),
        binding_unsigned(startup->identity),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_0(process_startup_obj, process_startup_binding);

static mp_obj_t process_call_binding(size_t count, const mp_obj_t *arguments)
{
    long number = binding_argument(arguments[0]);
    long first = count > 1 ? binding_argument(arguments[1]) : 0;
    long second = count > 2 ? binding_argument(arguments[2]) : 0;

    if (!takes_only_scalars(number)) {
        mp_raise_ValueError(MP_ERROR_TEXT("system call needs a typed binding"));
    }
    return binding_signed(process_call(first, second, 0, 0, 0, 0, number));
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(process_call_obj, SCALAR_ARGUMENTS_MIN, SCALAR_ARGUMENTS_MAX,
                                    process_call_binding);

static mp_obj_t process_spawn_binding(mp_obj_t system, mp_obj_t request)
{
    mp_buffer_info_t bytes;

    mp_get_buffer_raise(request, &bytes, MP_BUFFER_READ);
    if (bytes.len != SPAWN_REQUEST_BYTES) {
        mp_raise_ValueError(MP_ERROR_TEXT("spawn request has the wrong size"));
    }
    return binding_signed(process_call(binding_argument(system), (long)bytes.buf, 0, 0, 0, 0,
                                       SYSCALL_PROCESS_SPAWN));
}
MP_DEFINE_CONST_FUN_OBJ_2(process_spawn_obj, process_spawn_binding);

static mp_obj_t process_counters_binding(mp_obj_t system)
{
    uint8_t bytes[COUNTERS_BYTES];
    long status = process_call(binding_argument(system), (long)bytes, COUNTERS_BYTES, 0, 0, 0,
                               SYSCALL_SYSTEM_COUNTERS);
    mp_obj_tuple_t *counters;

    if (status < 0) {
        return binding_signed(status);
    }
    counters = MP_OBJ_TO_PTR(mp_obj_new_tuple(COUNTERS, NULL));
    for (size_t index = 0; index < COUNTERS; index++) {
        counters->items[index] = binding_unsigned(
            little_endian_read(bytes + index * DOUBLE_WORD_BYTES, DOUBLE_WORD_BYTES));
    }
    return MP_OBJ_FROM_PTR(counters);
}
MP_DEFINE_CONST_FUN_OBJ_1(process_counters_obj, process_counters_binding);
