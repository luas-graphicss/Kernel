#include "spawn_probe.h"

#include <stddef.h>
#include <stdint.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/process.h"
#include "kernel/diagnostics/console.h"
#include "kernel/diagnostics/counters.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/memory/string.h"
#include "kernel/processes/program.h"
#include "kernel/processes/spawn.h"
#include "kernel/processes/supervision.h"

#define PROGRAM_NAME "kernel_services.init.main"
#define PROGRAM_READY "ok"
#define ATTEMPT_LIMIT 4096u
#define QUOTA_SLACK_FRAMES 16u

static const uint32_t tracked_counters[] = {
    COUNTER_FRAMES_FREE, COUNTER_PROCESSES, COUNTER_OBJECTS,
    COUNTER_CAPABILITIES, COUNTER_ENDPOINTS, COUNTER_BUFFERS,
};

#define TRACKED_COUNTERS (sizeof(tracked_counters) / sizeof(tracked_counters[0]))

static bool resources_match(const uint64_t baseline[COUNTERS])
{
    uint64_t current[COUNTERS];

    resource_counters_read(current);
    for (size_t index = 0; index < TRACKED_COUNTERS; index++) {
        uint32_t counter = tracked_counters[index];

        if (current[counter] != baseline[counter]) {
            return false;
        }
    }
    return true;
}

static bool report(uint64_t refusals, const char *result)
{
    console_text("selftest: probe=spawn-failure");
    console_field_decimal("refusals", refusals);
    console_field_text("result", result);
    console_end_line();
    return false;
}

static int64_t spawn_with_budget(uint64_t allocations)
{
    struct frame_pool *pool = physical_memory_pool();
    struct spawn_quota quota = {
        .memory_frames = spawn_footprint_frames(0) + QUOTA_SLACK_FRAMES,
        .capabilities = PROFILE_CAPABILITIES_PER_PROCESS,
        .ipc_pending_bytes = PROFILE_IPC_PENDING_BYTES_PER_PROCESS,
    };
    int64_t handle;

    pool->allocations_before_failure = allocations;
    handle = spawn_initial(PROGRAM_NAME, sizeof(PROGRAM_NAME) - 1u, 0, quota);
    pool->allocations_before_failure = FRAME_UNLIMITED_ALLOCATIONS;
    return handle;
}

static bool tear_down(uint64_t handle)
{
    return supervision_kill(handle) == KERNEL_OK && supervision_release(handle) == KERNEL_OK;
}

bool spawn_probe_run(void)
{
    uint64_t baseline[COUNTERS];

    if (strcmp(program_prepare(), PROGRAM_READY) != 0) {
        return report(0, "program-unavailable");
    }
    resource_counters_read(baseline);
    for (uint64_t allocations = 0; allocations < ATTEMPT_LIMIT; allocations++) {
        int64_t handle = spawn_with_budget(allocations);

        if (handle > 0) {
            if (allocations == 0) {
                return report(allocations, "failure-not-injected");
            }
            if (!tear_down((uint64_t)handle) || !resources_match(baseline)) {
                return report(allocations, "teardown-leaked");
            }
            report(allocations, "ok");
            return true;
        }
        if (handle != -KERNEL_ERROR_OUT_OF_MEMORY) {
            return report(allocations, "unexpected-error");
        }
        if (!resources_match(baseline)) {
            return report(allocations, "refusal-leaked");
        }
    }
    return report(ATTEMPT_LIMIT, "never-admitted");
}
