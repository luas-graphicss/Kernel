#ifndef KERNEL_MEMORY_KERNEL_SPACE_H
#define KERNEL_MEMORY_KERNEL_SPACE_H

#include "kernel/memory/address_space.h"
#include "kernel/memory/page_table.h"
#include "kernel/startup/environment.h"

void kernel_space_init(const struct boot_environment *environment);
const struct page_tables *kernel_space_tables(void);
void kernel_space_activate(void);
void address_space_activate(const struct address_space *space);

#endif
