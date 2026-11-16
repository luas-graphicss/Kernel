#include "py/gc.h"
#include "shared/runtime/gchelper.h"

void gc_collect(void)
{
    gc_collect_start();
    gc_helper_collect_regs_and_stack();
    gc_collect_end();
}
