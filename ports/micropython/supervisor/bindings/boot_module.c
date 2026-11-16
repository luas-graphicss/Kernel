#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"
#include "kernel/processes/user_image.h"
#include "kernel/processes/user_process.h"
#include "kernel/startup/environment.h"

#define ABSENT_STATUS "absent"

static const uint8_t *boot_module_bytes(const struct boot_environment *environment)
{
    return (const uint8_t *)(uintptr_t)environment->description.boot_module.base;
}

static enum user_image_status parse_boot_module(const struct boot_environment *environment,
                                                struct user_image *image)
{
    return user_image_parse(boot_module_bytes(environment),
                            environment->description.boot_module.length, environment->user_region,
                            image);
}

static mp_obj_t supervisor_inspect_boot_module(void)
{
    const struct boot_environment *environment = boot_environment_current();
    struct user_image image = {0};
    const char *status = ABSENT_STATUS;

    if (environment->description.has_boot_module) {
        status = user_image_status_name(parse_boot_module(environment, &image));
    }
    mp_obj_t items[] = {
        mp_obj_new_str(status, strlen(status)),
        mp_obj_new_int_from_ull(image.file_bytes),
        mp_obj_new_int_from_ull(image.memory_bytes),
        mp_obj_new_int_from_ull(image.heap_bytes),
        mp_obj_new_int_from_ull(image.stack_bytes),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_inspect_boot_module_obj, supervisor_inspect_boot_module);

static mp_obj_t supervisor_run_boot_module(void)
{
    const struct boot_environment *environment = boot_environment_current();
    struct user_image image;
    struct user_exit outcome;

    if (!environment->description.has_boot_module ||
        parse_boot_module(environment, &image) != USER_IMAGE_OK) {
        mp_raise_ValueError(MP_ERROR_TEXT("boot module is not a valid user image"));
    }
    user_image_load(&image, boot_module_bytes(environment));
    outcome = user_process_run(&image, environment->user_region);

    mp_obj_t items[] = {
        MP_OBJ_NEW_QSTR(outcome.reason == USER_EXIT_REQUESTED ? MP_QSTR_exit : MP_QSTR_fault),
        mp_obj_new_int_from_ull(outcome.reason == USER_EXIT_REQUESTED ? outcome.status
                                                                      : outcome.cause),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_0(supervisor_run_boot_module_obj, supervisor_run_boot_module);
