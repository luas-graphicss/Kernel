#include "py/builtin.h"

mp_import_stat_t mp_import_stat(const char *path)
{
    (void)path;
    return MP_IMPORT_STAT_NO_EXIST;
}
