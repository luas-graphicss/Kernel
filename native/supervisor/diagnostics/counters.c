#include "kernel/diagnostics/counters.h"

#include "kernel/devices/device_registry.h"
#include "kernel/devices/interrupts.h"
#include "kernel/ipc/endpoint.h"
#include "kernel/memory/buffer.h"
#include "kernel/memory/buffer_pins.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/objects/kernel_objects.h"
#include "kernel/processes/process.h"

static struct activity_counters activity;

struct activity_counters *activity_counters(void)
{
    return &activity;
}

void resource_counters_read(uint64_t counters[COUNTERS])
{
    const struct frame_pool *pool = physical_memory_pool();
    struct ipc_usage ipc = endpoint_usage();

    counters[COUNTER_FRAMES_USABLE] = pool->usable_frames;
    counters[COUNTER_FRAMES_FREE] = pool->free_frames;
    counters[COUNTER_FRAMES_RESERVED] = pool->reserve_frames;
    counters[COUNTER_PROCESSES] = process_live_count();
    counters[COUNTER_OBJECTS] = kernel_object_table()->slots.live;
    counters[COUNTER_CAPABILITIES] = kernel_capabilities()->live;
    counters[COUNTER_ENDPOINTS] = ipc.endpoints;
    counters[COUNTER_MESSAGES] = ipc.messages;
    counters[COUNTER_IPC_BYTES] = ipc.pending_bytes;
    counters[COUNTER_BUFFERS] = buffer_live_count();
    counters[COUNTER_DROPPED_EVENTS] = process_events_dropped();
    counters[COUNTER_USER_FAULTS] = activity.user_faults;
    counters[COUNTER_CONTEXT_SWITCHES] = activity.context_switches;
    counters[COUNTER_PREEMPTIONS] = activity.preemptions;
    counters[COUNTER_REFUSED_ALLOCATIONS] = pool->refused_allocations;
    counters[COUNTER_TIMER_INTERRUPTS] = activity.timer_interrupts;
    counters[COUNTER_EXTERNAL_INTERRUPTS] = interrupts_handled();
    counters[COUNTER_DEVICE_REQUESTS] = device_registry_requests();
    counters[COUNTER_PINNED_BUFFERS] = buffer_pinned_count();
    counters[COUNTER_QUARANTINED_DEVICES] = device_registry_quarantined();
}
