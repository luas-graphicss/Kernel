#ifndef KERNEL_PROCESSES_PROCESS_H
#define KERNEL_PROCESSES_PROCESS_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/abi/process.h"
#include "kernel/arch/user_context.h"
#include "kernel/events/event_queue.h"
#include "kernel/memory/address_space.h"
#include "kernel/processes/spawn_request.h"

#define PROCESS_NONE UINT32_MAX
#define PROCESS_BUFFER_MAPPINGS 16u
#define WAIT_CHAIN_LIMIT 8u
#define ENVIRONMENT_CALL_BYTES 4u

#define EVENT_READY 1u
#define EVENT_EXITED 2u

enum process_state {
    PROCESS_FREE,
    PROCESS_NEW,
    PROCESS_READY,
    PROCESS_RUNNING,
    PROCESS_BLOCKED,
    PROCESS_DYING,
};

enum wait_kind {
    WAIT_NONE,
    WAIT_RECEIVE,
    WAIT_SEND,
    WAIT_REPLY,
    WAIT_PROCESS,
};

struct process_wait {
    enum wait_kind kind;
    bool restarts;
    uint32_t depends_on;
    uint64_t deadline;
    uint64_t object;
    uint64_t sequence;
    uint64_t response_address;
    uint64_t response_capacity;
    uint64_t control_address;
    uint64_t correlation;
};

struct buffer_mapping {
    bool used;
    bool writable;
    uint32_t buffer;
    uint64_t object;
    uint64_t address;
    uint64_t bytes;
};

struct process {
    enum process_state state;
    uint32_t index;
    uint64_t handle;
    uint64_t object;
    struct address_space space;
    struct user_context context;
    struct process_wait wait;
    struct buffer_mapping mappings[PROCESS_BUFFER_MAPPINGS];
    uint64_t memory_quota_frames;
    uint64_t buffer_frames;
    uint64_t ipc_quota_bytes;
    uint64_t ipc_pending_bytes;
    uint32_t exit_reason;
    uint64_t exit_value;
};

struct process_request {
    const char *name;
    uint32_t name_length;
    const uint8_t *argument;
    uint32_t argument_length;
    uint64_t heap_bytes;
    uint64_t memory_quota_frames;
    uint32_t capability_limit;
    uint64_t ipc_quota_bytes;
    uint32_t parent;
    const struct spawn_grant *grants;
    uint32_t grant_count;
    bool grants_system;
};

void process_table_init(void);
struct process *process_at(uint32_t index);
struct process *process_find(uint64_t handle);
struct process *process_allocate(void);
void process_free(struct process *process);
uint32_t process_capacity(void);
uint32_t process_live_count(void);
uint64_t process_memory_frames(const struct process *process);
void process_set_result(struct process *process, int64_t value);

void process_event_push(uint32_t kind, uint64_t handle);
bool process_event_pop(struct kernel_event *event);
bool process_events_pending(void);
bool process_events_take_overflow(void);
uint64_t process_events_dropped(void);

void wait_begin(struct process *process, enum wait_kind kind, bool restarts, uint64_t object,
                uint64_t deadline, uint32_t depends_on);
void wait_restart(struct process *process);
void wait_complete(struct process *process, int64_t result);
void wait_finish(struct process *process, int64_t result);
void wait_expire(uint64_t now);
uint64_t wait_earliest_deadline(void);
int64_t wait_chain_check(const struct process *waiter, uint32_t target);
void wait_wake_exit_waiters(uint64_t handle);

int64_t process_create(const struct process_request *request);
void process_terminate(struct process *process, uint32_t reason, uint64_t value);
void process_reap(uint64_t handle);

#endif
