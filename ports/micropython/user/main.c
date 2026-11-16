#include <stdbool.h>

#include "lifecycle/runtime.h"
#include "process_calls.h"

#define ENTRY_MODULE "kernel_services.init.main"
#define EXIT_SUCCEEDED 0u
#define EXIT_FAILED 1u

_Noreturn void user_main(void);

_Noreturn void user_main(void)
{
    bool succeeded;

    runtime_start();
    succeeded = runtime_run_entry(ENTRY_MODULE);
    runtime_stop();
    process_exit(succeeded ? EXIT_SUCCEEDED : EXIT_FAILED);
}
