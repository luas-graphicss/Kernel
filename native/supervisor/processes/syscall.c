#include "kernel/processes/syscall.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/process.h"
#include "kernel/abi/syscalls.h"
#include "kernel/diagnostics/console.h"
#include "kernel/timers/clock.h"
#include "kernel/timers/timer.h"

#define EXIT_STATUS_MASK 0xffffffffull

static struct syscall_result process_exit(struct process *caller, const uint64_t *arguments)
{
    process_terminate(caller, WAIT_REASON_EXIT, arguments[0] & EXIT_STATUS_MASK);
    return (struct syscall_result){.action = SYSCALL_EXIT};
}

static struct syscall_result debug_write(struct process *caller, const uint64_t *arguments)
{
    char text[SYSCALL_DEBUG_WRITE_MAX_BYTES];
    uint64_t length = arguments[1];

    if (length > SYSCALL_DEBUG_WRITE_MAX_BYTES) {
        return syscall_resume(-KERNEL_ERROR_MESSAGE_TOO_LARGE);
    }
    if (length == 0) {
        return syscall_resume(0);
    }
    if (!user_memory_read(&caller->space, arguments[0], text, length)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    console_write(text, (size_t)length);
    return syscall_resume((int64_t)length);
}

static struct syscall_result clock_now(struct process *caller, const uint64_t *arguments)
{
    uint64_t now = timer_now_nanoseconds();

    (void)caller;
    (void)arguments;
    return syscall_resume(now > INT64_MAX ? INT64_MAX : (int64_t)now);
}

static struct syscall_result process_yield(struct process *caller, const uint64_t *arguments)
{
    (void)caller;
    (void)arguments;
    return (struct syscall_result){.action = SYSCALL_YIELD};
}

static const syscall_handler handlers[SYSCALL_COUNT] = {
    [SYSCALL_PROCESS_EXIT] = process_exit,
    [SYSCALL_DEBUG_WRITE] = debug_write,
    [SYSCALL_CLOCK_NOW] = clock_now,
    [SYSCALL_PROCESS_YIELD] = process_yield,
    [SYSCALL_CAPABILITY_CLOSE] = syscall_capability_close,
    [SYSCALL_CAPABILITY_DERIVE] = syscall_capability_derive,
    [SYSCALL_CAPABILITY_REVOKE] = syscall_capability_revoke,
    [SYSCALL_CAPABILITY_INSPECT] = syscall_capability_inspect,
    [SYSCALL_ENDPOINT_CREATE] = syscall_endpoint_create,
    [SYSCALL_IPC_SEND] = syscall_ipc_send,
    [SYSCALL_IPC_RECEIVE] = syscall_ipc_receive,
    [SYSCALL_IPC_CALL] = syscall_ipc_call,
    [SYSCALL_IPC_REPLY] = syscall_ipc_reply,
    [SYSCALL_BUFFER_CREATE] = syscall_buffer_create,
    [SYSCALL_BUFFER_MAP] = syscall_buffer_map,
    [SYSCALL_BUFFER_UNMAP] = syscall_buffer_unmap,
    [SYSCALL_PROCESS_SPAWN] = syscall_process_spawn,
    [SYSCALL_PROCESS_WAIT] = syscall_process_wait,
    [SYSCALL_PROCESS_KILL] = syscall_process_kill,
    [SYSCALL_PROCESS_INTERRUPT] = syscall_process_interrupt,
    [SYSCALL_SYSTEM_COUNTERS] = syscall_system_counters,
    [SYSCALL_DEVICE_LIST] = syscall_device_list,
    [SYSCALL_DEVICE_CLAIM] = syscall_device_claim,
    [SYSCALL_DEVICE_OPEN] = syscall_device_open,
    [SYSCALL_DEVICE_CONFIG] = syscall_device_config,
    [SYSCALL_DEVICE_SUBMIT] = syscall_device_submit,
    [SYSCALL_DEVICE_WAIT] = syscall_device_wait,
    [SYSCALL_DEVICE_RESET] = syscall_device_reset,
    [SYSCALL_SERIAL_WRITE] = syscall_serial_write,
    [SYSCALL_SERIAL_READ] = syscall_serial_read,
};

struct syscall_result syscall_dispatch(struct process *caller, const struct syscall_request *request)
{
    if (request->number >= SYSCALL_COUNT) {
        return syscall_resume(-KERNEL_ERROR_UNSUPPORTED);
    }
    return handlers[request->number](caller, request->arguments);
}

struct syscall_result syscall_resume(int64_t value)
{
    return (struct syscall_result){.action = SYSCALL_RESUME, .value = value};
}

struct syscall_result syscall_block(void)
{
    return (struct syscall_result){.action = SYSCALL_BLOCK};
}

bool syscall_deadline(uint64_t nanoseconds, uint64_t *ticks)
{
    if (nanoseconds == DEADLINE_NEVER) {
        *ticks = CLOCK_NEVER;
        return true;
    }
    if (nanoseconds <= timer_now_nanoseconds()) {
        return false;
    }
    *ticks = timer_ticks_from_nanoseconds(nanoseconds);
    return true;
}
