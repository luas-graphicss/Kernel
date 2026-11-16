#include "lifecycle/runtime.h"

#include "py/cstack.h"
#include "py/gc.h"
#include "py/nlr.h"
#include "py/obj.h"
#include "py/qstr.h"
#include "py/runtime.h"

#include "platform.h"

void runtime_start(void)
{
    struct runtime_memory memory = platform_runtime_memory();

    mp_cstack_init_with_top(memory.stack_top, memory.stack_bytes);
    gc_init(memory.heap_start, memory.heap_end);
    mp_init();
    mp_sys_path = mp_obj_new_list(0, NULL);
    mp_obj_list_append(mp_sys_path, MP_OBJ_NEW_QSTR(MP_QSTR__dot_frozen));
}

bool runtime_run_entry(const char *module_name)
{
    nlr_buf_t nlr;

    if (nlr_push(&nlr) != 0) {
        mp_obj_print_exception(&mp_plat_print, MP_OBJ_FROM_PTR(nlr.ret_val));
        return false;
    }
    mp_obj_t module =
        mp_import_name(qstr_from_str(module_name), mp_const_true, MP_OBJ_NEW_SMALL_INT(0));
    mp_obj_t outcome = mp_call_function_0(mp_load_attr(module, MP_QSTR_main));
    bool succeeded = mp_obj_is_true(outcome);
    nlr_pop();
    return succeeded;
}

void runtime_stop(void)
{
    mp_deinit();
}
