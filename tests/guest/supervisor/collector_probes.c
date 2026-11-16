#include "collector_probes.h"

#include <stddef.h>
#include <stdint.h>

#include "kernel/diagnostics/console.h"
#include "memory/heap.h"

#define PROBE_ROUNDS 32u
#define CHURN_BLOCKS 48u
#define CHURN_BYTES 96u

typedef int (*collector_probe)(void);

struct named_probe {
    const char *root;
    collector_probe run;
};

static const struct named_probe probes[] = {
    {"s0", collector_probe_register_s0},   {"s1", collector_probe_register_s1},
    {"s2", collector_probe_register_s2},   {"s3", collector_probe_register_s3},
    {"s4", collector_probe_register_s4},   {"s5", collector_probe_register_s5},
    {"s6", collector_probe_register_s6},   {"s7", collector_probe_register_s7},
    {"s8", collector_probe_register_s8},   {"s9", collector_probe_register_s9},
    {"s10", collector_probe_register_s10}, {"s11", collector_probe_register_s11},
    {"stack-slot", collector_probe_stack_slot},
};

#define PROBE_COUNT (sizeof(probes) / sizeof(probes[0]))

static void churn_heap(void)
{
    for (size_t index = 0; index < CHURN_BLOCKS; index++) {
        (void)runtime_heap_allocate(CHURN_BYTES);
    }
}

static const char *outcome_name(int outcome)
{
    switch (outcome) {
    case COLLECTOR_PROBE_PASSED:
        return "ok";
    case COLLECTOR_PROBE_ROOT_COLLECTED:
        return "root-collected";
    case COLLECTOR_PROBE_DECOY_RETAINED:
        return "decoy-retained";
    default:
        return "unknown";
    }
}

static void report(const char *root, uint64_t rounds, int outcome)
{
    console_text("selftest: probe=gc-roots");
    console_field_text("root", root);
    console_field_decimal("rounds", rounds);
    console_field_text("result", outcome_name(outcome));
    console_end_line();
}

bool collector_probes_run(void)
{
    for (size_t index = 0; index < PROBE_COUNT; index++) {
        for (uint64_t round = 0; round < PROBE_ROUNDS; round++) {
            int outcome = probes[index].run();

            if (outcome != COLLECTOR_PROBE_PASSED) {
                report(probes[index].root, round, outcome);
                return false;
            }
            churn_heap();
        }
        report(probes[index].root, PROBE_ROUNDS, COLLECTOR_PROBE_PASSED);
    }
    return true;
}
