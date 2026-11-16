#ifndef KERNEL_PROCESSES_SYSCALL_H
#define KERNEL_PROCESSES_SYSCALL_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/processes/process.h"

#define SYSCALL_ARGUMENTS 6u

enum syscall_action {
    SYSCALL_RESUME,
    SYSCALL_BLOCK,
    SYSCALL_YIELD,
    SYSCALL_EXIT,
    SYSCALL_SPAWN,
};

struct syscall_request {
    uint64_t number;
    uint64_t arguments[SYSCALL_ARGUMENTS];
};

struct syscall_result {
    enum syscall_action action;
    int64_t value;
};

typedef struct syscall_result (*syscall_handler)(struct process *caller, const uint64_t *arguments);

struct syscall_result syscall_dispatch(struct process *caller,
                                       const struct syscall_request *request);
struct syscall_result syscall_resume(int64_t value);
struct syscall_result syscall_block(void);
bool syscall_deadline(uint64_t nanoseconds, uint64_t *ticks);

struct syscall_result syscall_capability_close(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_capability_derive(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_capability_revoke(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_capability_inspect(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_endpoint_create(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_ipc_send(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_ipc_receive(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_ipc_call(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_ipc_reply(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_buffer_create(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_buffer_map(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_buffer_unmap(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_process_spawn(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_process_wait(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_process_kill(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_process_interrupt(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_system_counters(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_device_list(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_device_claim(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_device_open(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_device_config(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_device_submit(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_device_wait(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_device_reset(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_serial_write(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_serial_read(struct process *caller, const uint64_t *arguments);
struct syscall_result syscall_system_power(struct process *caller, const uint64_t *arguments);

#endif
