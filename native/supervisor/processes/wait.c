#include "kernel/processes/process.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/ipc/call.h"
#include "kernel/timers/clock.h"

static uint64_t sequence;

static void make_ready(struct process *process)
{
    process->wait = (struct process_wait){.depends_on = PROCESS_NONE};
    process->state = PROCESS_READY;
    process_event_push(EVENT_READY, process->handle);
}

void wait_begin(struct process *process, enum wait_kind kind, bool restarts, uint64_t object,
                uint64_t deadline, uint32_t depends_on)
{
    sequence++;
    process->wait = (struct process_wait){
        .kind = kind,
        .restarts = restarts,
        .depends_on = depends_on,
        .deadline = deadline,
        .object = object,
        .sequence = sequence,
    };
    if (restarts) {
        process->context.frame.program_counter -= ENVIRONMENT_CALL_BYTES;
    }
    process->state = PROCESS_BLOCKED;
}

void wait_restart(struct process *process)
{
    if (process->state == PROCESS_BLOCKED) {
        make_ready(process);
    }
}

void wait_complete(struct process *process, int64_t result)
{
    if (process->state != PROCESS_BLOCKED) {
        return;
    }
    if (process->wait.restarts) {
        process->context.frame.program_counter += ENVIRONMENT_CALL_BYTES;
    }
    process_set_result(process, result);
    make_ready(process);
}

void wait_finish(struct process *process, int64_t result)
{
    if (process->state != PROCESS_BLOCKED) {
        return;
    }
    if (process->wait.kind == WAIT_REPLY) {
        call_abandon(process);
    }
    wait_complete(process, result);
}

void wait_expire(uint64_t now)
{
    for (uint32_t index = 0; index < process_capacity(); index++) {
        struct process *process = process_at(index);

        if (process->state == PROCESS_BLOCKED && process->wait.deadline != CLOCK_NEVER &&
            process->wait.deadline <= now) {
            wait_finish(process, -KERNEL_ERROR_TIMED_OUT);
        }
    }
}

uint64_t wait_earliest_deadline(void)
{
    uint64_t earliest = CLOCK_NEVER;

    for (uint32_t index = 0; index < process_capacity(); index++) {
        const struct process *process = process_at(index);

        if (process->state == PROCESS_BLOCKED && process->wait.deadline < earliest) {
            earliest = process->wait.deadline;
        }
    }
    return earliest;
}

int64_t wait_chain_check(const struct process *waiter, uint32_t target)
{
    uint32_t current = target;

    for (uint32_t depth = 0; depth < WAIT_CHAIN_LIMIT; depth++) {
        const struct process *process = process_at(current);

        if (current == waiter->index) {
            return -KERNEL_ERROR_WOULD_DEADLOCK;
        }
        if (process == NULL || process->state != PROCESS_BLOCKED ||
            process->wait.depends_on == PROCESS_NONE) {
            return KERNEL_OK;
        }
        current = process->wait.depends_on;
    }
    return -KERNEL_ERROR_LIMIT_EXCEEDED;
}

void wait_wake_exit_waiters(uint64_t handle)
{
    for (uint32_t index = 0; index < process_capacity(); index++) {
        struct process *process = process_at(index);

        if (process->state == PROCESS_BLOCKED && process->wait.kind == WAIT_PROCESS &&
            process->wait.object == handle) {
            wait_restart(process);
        }
    }
}
