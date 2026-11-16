#include "kernel/processes/run.h"

#include <stddef.h>

#include "kernel/abi/process.h"
#include "kernel/arch/interrupts.h"
#include "kernel/devices/device_registry.h"
#include "kernel/devices/interrupts.h"
#include "kernel/diagnostics/console.h"
#include "kernel/diagnostics/counters.h"
#include "kernel/memory/kernel_space.h"
#include "kernel/processes/process.h"
#include "kernel/processes/syscall.h"
#include "kernel/timers/clock.h"
#include "kernel/timers/timer.h"

static struct syscall_request read_request(const struct trap_frame *frame)
{
    struct syscall_request request = {.number = frame->registers[REGISTER_SYSCALL_NUMBER]};

    for (size_t index = 0; index < SYSCALL_ARGUMENTS; index++) {
        request.arguments[index] = frame->registers[REGISTER_ARGUMENT_FIRST + index];
    }
    return request;
}

static void report_fault(const struct process *process)
{
    const struct trap_frame *frame = &process->context.frame;

    console_text("user: fault");
    console_field_text("cause", trap_cause_name(frame->cause));
    console_field_hex("scause", frame->cause);
    console_field_hex("sepc", frame->program_counter);
    console_field_hex("stval", frame->value);
    console_field_decimal("process", process->index);
    console_end_line();
}

static struct run_outcome leave(uint32_t result, uint64_t value, uint64_t detail)
{
    timer_disarm();
    return (struct run_outcome){.result = result, .value = value, .detail = detail};
}

static struct run_outcome suspend(struct process *process, uint32_t result)
{
    process->state = PROCESS_READY;
    return leave(result, 0, 0);
}

static struct run_outcome exited(const struct process *process)
{
    return leave(RUN_EXITED, process->exit_reason, process->exit_value);
}

static struct run_outcome blocked(const struct process *process)
{
    const struct process *dependency = NULL;

    if (process->wait.kind == WAIT_REPLY || process->wait.kind == WAIT_SEND) {
        dependency = process_at(process->wait.depends_on);
    }
    return leave(RUN_BLOCKED, dependency != NULL ? dependency->handle : 0, 0);
}

static void enter_user(struct process *process, uint64_t quantum_end)
{
    uint64_t deadline = wait_earliest_deadline();

    process->context.frame.status = user_context_status();
    timer_arm(deadline < quantum_end ? deadline : quantum_end);
    address_space_activate(&process->space);
    user_context_enter(&process->context);
    kernel_space_activate();
}

static bool is_external_interrupt(uint64_t cause)
{
    return trap_is_interrupt(cause) &&
           trap_interrupt_number(cause) == TRAP_CAUSE_SUPERVISOR_EXTERNAL;
}

static bool quantum_expired(uint64_t quantum_end)
{
    uint64_t now = timer_now();

    timer_disarm();
    activity_counters()->timer_interrupts++;
    wait_expire(now);
    return now >= quantum_end || process_events_pending();
}

struct run_outcome supervisor_run(uint64_t handle, uint64_t quantum_nanoseconds)
{
    struct process *process = process_find(handle);
    struct trap_frame *frame;
    uint64_t quantum_end;

    if (process == NULL || process->state != PROCESS_READY) {
        return (struct run_outcome){.result = RUN_STALE};
    }
    frame = &process->context.frame;
    quantum_end = clock_add(timer_now(), timer_ticks_from_nanoseconds(quantum_nanoseconds));
    process->state = PROCESS_RUNNING;
    activity_counters()->context_switches++;
    for (;;) {
        struct syscall_request request;
        struct syscall_result result;

        enter_user(process, quantum_end);
        if (is_external_interrupt(frame->cause)) {
            interrupts_dispatch();
            if (process_events_pending()) {
                return suspend(process, RUN_PREEMPTED);
            }
            continue;
        }
        if (trap_is_interrupt(frame->cause)) {
            if (quantum_expired(quantum_end)) {
                activity_counters()->preemptions++;
                return suspend(process, RUN_PREEMPTED);
            }
            continue;
        }
        if (frame->cause != TRAP_CAUSE_USER_ENVIRONMENT_CALL) {
            activity_counters()->user_faults++;
            report_fault(process);
            process_terminate(process, WAIT_REASON_FAULT, frame->cause);
            return exited(process);
        }
        frame->program_counter += ENVIRONMENT_CALL_BYTES;
        request = read_request(frame);
        result = syscall_dispatch(process, &request);
        switch (result.action) {
        case SYSCALL_RESUME:
            process_set_result(process, result.value);
            if (process_events_pending()) {
                return suspend(process, RUN_PREEMPTED);
            }
            break;
        case SYSCALL_BLOCK:
            return blocked(process);
        case SYSCALL_YIELD:
            process_set_result(process, 0);
            return suspend(process, RUN_YIELDED);
        case SYSCALL_EXIT:
            return exited(process);
        case SYSCALL_SPAWN:
            return suspend(process, RUN_SPAWN);
        }
    }
}

bool supervisor_idle(void)
{
    uint64_t deadline = wait_earliest_deadline();

    if (deadline == CLOCK_NEVER && !device_registry_has_waiters()) {
        return false;
    }
    timer_wait_until(deadline);
    interrupts_dispatch();
    wait_expire(timer_now());
    return true;
}
