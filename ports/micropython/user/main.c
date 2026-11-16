#include <stdbool.h>
#include <stdint.h>

#include "lifecycle/runtime.h"
#include "process_calls.h"
#include "startup.h"

#define EXIT_SUCCEEDED 0u
#define EXIT_FAILED 1u

_Noreturn void user_main(const uint8_t *startup_block);

_Noreturn void user_main(const uint8_t *startup_block)
{
    bool succeeded;

    process_startup_load(startup_block);
    runtime_start();
    succeeded = runtime_run_entry(process_startup()->name);
    runtime_stop();
    process_exit(succeeded ? EXIT_SUCCEEDED : EXIT_FAILED);
}
