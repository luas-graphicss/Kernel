#ifndef KERNEL_PROCESSES_PROGRAM_H
#define KERNEL_PROCESSES_PROGRAM_H

#include <stdint.h>

#include "kernel/memory/address_space.h"
#include "kernel/processes/user_image.h"

const char *program_prepare(void);
const struct user_image *program_image(void);
struct memory_range program_region(void);
struct memory_range program_address_range(void);
enum page_status program_load(struct address_space *space, const struct user_layout *layout);

#endif
