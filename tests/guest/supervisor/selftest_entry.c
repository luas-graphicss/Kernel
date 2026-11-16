#include "kernel/startup/policy.h"

#include <stddef.h>

#include "collector_probes.h"
#include "kernel/memory/string.h"
#include "kernel/startup/environment.h"
#include "lifecycle/runtime.h"
#include "memory/heap.h"
#include "restart_probe.h"
#include "spawn_probe.h"
#include "trap_probe.h"

#define SELFTEST_MODULE "runtime_selftest.main"
#define TRAP_PROBE_ARGUMENT "probe=supervisor-trap"
#define RUNTIME_TRAP_PROBE_ARGUMENT "probe=runtime-trap"
#define SPAWN_PROBE_ARGUMENT "probe=spawn-failure"
#define EXHAUSTING_BLOCK_BYTES 1024u

static bool probe_requested(const char *probe)
{
    const char *arguments = boot_environment_current()->description.arguments;

    return arguments != NULL && strcmp(arguments, probe) == 0;
}

static void exhaust_runtime_heap(void)
{
    void **held = NULL;
    void **block = runtime_heap_allocate(EXHAUSTING_BLOCK_BYTES);

    while (block != NULL) {
        *block = held;
        held = block;
        block = runtime_heap_allocate(EXHAUSTING_BLOCK_BYTES);
    }
}

bool supervisor_policy_run(void)
{
    bool succeeded;

    if (probe_requested(TRAP_PROBE_ARGUMENT)) {
        trap_probe_illegal_instruction();
    }
    if (probe_requested(SPAWN_PROBE_ARGUMENT)) {
        return spawn_probe_run();
    }
    runtime_start();
    if (probe_requested(RUNTIME_TRAP_PROBE_ARGUMENT)) {
        exhaust_runtime_heap();
        trap_probe_illegal_instruction();
    }
    succeeded = collector_probes_run() && runtime_run_entry(SELFTEST_MODULE);
    runtime_stop();
    return succeeded && restart_probe_run();
}
