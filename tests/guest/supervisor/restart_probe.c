#include "restart_probe.h"

#include <stdint.h>

#include "kernel/diagnostics/console.h"
#include "lifecycle/runtime.h"
#include "memory/heap.h"

#define RESTART_CYCLES 8u
#define RESTART_MODULE "runtime_selftest.restart"

struct cycle_usage {
    struct runtime_heap_usage started;
    struct runtime_heap_usage finished;
    bool entry_succeeded;
};

static struct cycle_usage run_cycle(void)
{
    struct cycle_usage usage;

    runtime_start();
    usage.started = runtime_heap_usage();
    usage.entry_succeeded = runtime_run_entry(RESTART_MODULE);
    runtime_heap_collect();
    usage.finished = runtime_heap_usage();
    runtime_stop();
    return usage;
}

static bool same_usage(struct runtime_heap_usage first, struct runtime_heap_usage second)
{
    return first.total_bytes == second.total_bytes && first.used_bytes == second.used_bytes &&
           first.free_bytes == second.free_bytes;
}

static bool report(uint64_t cycles, const struct cycle_usage *usage, const char *result)
{
    console_text("selftest: probe=runtime-restart");
    console_field_decimal("cycles", cycles);
    console_field_decimal("heap-bytes", usage->started.total_bytes);
    console_field_decimal("used-after-start", usage->started.used_bytes);
    console_field_decimal("used-after-run", usage->finished.used_bytes);
    console_field_text("result", result);
    console_end_line();
    return false;
}

bool restart_probe_run(void)
{
    struct cycle_usage baseline = run_cycle();

    if (!baseline.entry_succeeded) {
        return report(0, &baseline, "entry-failed");
    }
    for (uint64_t cycle = 1; cycle < RESTART_CYCLES; cycle++) {
        struct cycle_usage usage = run_cycle();

        if (!usage.entry_succeeded) {
            return report(cycle, &usage, "entry-failed");
        }
        if (!same_usage(usage.started, baseline.started) ||
            !same_usage(usage.finished, baseline.finished)) {
            return report(cycle, &usage, "usage-drift");
        }
    }
    report(RESTART_CYCLES, &baseline, "ok");
    return true;
}
