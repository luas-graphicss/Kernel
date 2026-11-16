#include "kernel/startup/policy.h"

#include "lifecycle/runtime.h"

#define POLICY_ENTRY_MODULE "kernel_core.bootstrap"

bool supervisor_policy_run(void)
{
    bool succeeded;

    runtime_start();
    succeeded = runtime_run_entry(POLICY_ENTRY_MODULE);
    runtime_stop();
    return succeeded;
}
