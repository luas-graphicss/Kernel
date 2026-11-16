#ifndef KERNEL_PROCESSES_USER_PROCESS_H
#define KERNEL_PROCESSES_USER_PROCESS_H

#include <stdint.h>

#include "kernel/memory/range.h"
#include "kernel/processes/user_image.h"

enum user_exit_reason {
    USER_EXIT_REQUESTED,
    USER_EXIT_FAULT,
};

struct user_exit {
    enum user_exit_reason reason;
    uint32_t status;
    uint64_t cause;
};

void user_image_load(const struct user_image *image, const uint8_t *module);
struct user_exit user_process_run(const struct user_image *image, struct memory_range region);

#endif
