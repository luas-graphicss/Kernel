#include "targets.h"

#include <stdio.h>
#include <stdlib.h>

static const fuzz_entry entries[] = {
    fuzz_device_tree,
    fuzz_user_image,
    fuzz_ipc_message,
    fuzz_spawn_request,
};

fuzz_entry fuzz_target_entry(unsigned long index)
{
    if (index >= sizeof(entries) / sizeof(entries[0])) {
        return NULL;
    }
    return entries[index];
}

_Noreturn void fuzz_invariant_violated(const char *invariant)
{
    fprintf(stderr, "invariant violated: %s\n", invariant);
    abort();
}
