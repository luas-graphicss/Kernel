#include "py/gc.h"
#include "shared/runtime/gchelper.h"

#include "platform.h"

void gc_collect(void)
{
    platform_collection_begins();
    gc_collect_start();
    gc_helper_collect_regs_and_stack();
    gc_collect_end();
    platform_collection_ends();
}
