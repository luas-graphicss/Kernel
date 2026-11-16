#include "py/builtin.h"
#include "py/lexer.h"
#include "py/mperrno.h"
#include "py/runtime.h"

mp_import_stat_t mp_import_stat(const char *path)
{
    (void)path;
    return MP_IMPORT_STAT_NO_EXIST;
}

#if MICROPY_ENABLE_COMPILER
mp_lexer_t *mp_lexer_new_from_file(qstr filename)
{
    (void)filename;
    mp_raise_OSError(MP_ENOENT);
}
#endif
