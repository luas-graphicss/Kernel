#include "kernel/processes/process.h"

#include <stddef.h>

#include "kernel/objects/slot_table.h"

#define EVENT_CAPACITY 64u

static struct process processes[PROFILE_PROCESSES];
static struct slot_record records[PROFILE_PROCESSES];
static struct slot_table slots;
static struct kernel_event event_slots[EVENT_CAPACITY];
static struct event_queue events;

static void reset(struct process *process, uint32_t index)
{
    *process = (struct process){.index = index, .wait = {.depends_on = PROCESS_NONE}};
}

void process_table_init(void)
{
    slot_table_init(&slots, records, PROFILE_PROCESSES, SLOT_MAX_GENERATION);
    event_queue_init(&events, event_slots, EVENT_CAPACITY);
    for (uint32_t index = 0; index < PROFILE_PROCESSES; index++) {
        reset(&processes[index], index);
    }
}

struct process *process_at(uint32_t index)
{
    return index < PROFILE_PROCESSES ? &processes[index] : NULL;
}

struct process *process_find(uint64_t handle)
{
    uint32_t index;

    if (!slot_table_resolve(&slots, handle, &index)) {
        return NULL;
    }
    return &processes[index];
}

struct process *process_allocate(void)
{
    uint64_t handle = slot_table_allocate(&slots);
    struct process *process;

    if (handle == SLOT_INVALID_HANDLE) {
        return NULL;
    }
    process = &processes[handle & SLOT_INDEX_MASK];
    reset(process, (uint32_t)(handle & SLOT_INDEX_MASK));
    process->state = PROCESS_NEW;
    process->handle = handle;
    return process;
}

void process_free(struct process *process)
{
    slot_table_release(&slots, process->handle);
    reset(process, process->index);
}

uint32_t process_capacity(void)
{
    return slots.capacity;
}

uint32_t process_live_count(void)
{
    return slots.live;
}

uint64_t process_memory_frames(const struct process *process)
{
    return address_space_frames(&process->space) + process->buffer_frames;
}

void process_set_result(struct process *process, int64_t value)
{
    process->context.frame.registers[REGISTER_ARGUMENT_FIRST] = (uint64_t)value;
}

void process_event_push(uint32_t kind, uint64_t handle)
{
    event_queue_push(&events, (struct kernel_event){.kind = kind, .subject = handle});
}

bool process_event_pop(struct kernel_event *event)
{
    return event_queue_pop(&events, event);
}

bool process_events_pending(void)
{
    return events.count != 0 || events.overflowed;
}

bool process_events_take_overflow(void)
{
    return event_queue_take_overflow(&events);
}

uint64_t process_events_dropped(void)
{
    return events.dropped;
}
