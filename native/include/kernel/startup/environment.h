#ifndef KERNEL_STARTUP_ENVIRONMENT_H
#define KERNEL_STARTUP_ENVIRONMENT_H

#include <stdint.h>

#include "kernel/devices/device_tree.h"
#include "kernel/memory/layout.h"
#include "kernel/memory/range.h"

struct boot_environment {
    uint64_t hart;
    struct boot_description description;
    struct memory_layout layout;
    struct memory_range device_tree;
    struct memory_range supervisor_heap;
    struct memory_range user_region;
};

const struct boot_environment *boot_environment_load(uint64_t hart, const void *device_tree_blob);
const struct boot_environment *boot_environment_current(void);
_Noreturn void supervisor_main(uint64_t hart, const void *device_tree_blob);

#endif
