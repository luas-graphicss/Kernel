#include "py/mpprint.h"
#include "py/nlr.h"

#include "platform.h"

void nlr_jump_fail(void *value)
{
    (void)value;
    platform_fatal("uncaught-runtime-exception");
}

void __assert_func(const char *file, int line, const char *function, const char *expression)
{
    mp_printf(&mp_plat_print, "runtime: assertion=\"%s\" function=%s file=%s line=%d\n", expression,
              function, file, line);
    platform_fatal("runtime-assertion");
}
