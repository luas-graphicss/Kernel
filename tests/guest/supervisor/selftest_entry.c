#include "kernel/startup/policy.h"

#include <stddef.h>

#include "collector_probes.h"
#include "kernel/memory/string.h"
#include "kernel/startup/environment.h"
#include "lifecycle/runtime.h"
#include "restart_probe.h"
#include "trap_probe.h"

#define SELFTEST_MODULE "runtime_selftest.main"
#define TRAP_PROBE_ARGUMENT "probe=supervisor-trap"

static bool trap_probe_requested(void)
{
    const char *arguments = boot_environment_current()->description.arguments;

    return arguments != NULL && strcmp(arguments, TRAP_PROBE_ARGUMENT) == 0;
}

bool supervisor_policy_run(void)
{
    bool succeeded;

    if (trap_probe_requested()) {
        trap_probe_illegal_instruction();
    }
    runtime_start();
    succeeded = collector_probes_run() && runtime_run_entry(SELFTEST_MODULE);
    runtime_stop();
    return succeeded && restart_probe_run();
}
