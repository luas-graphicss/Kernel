#ifndef KERNEL_PORT_LIFECYCLE_RUNTIME_H
#define KERNEL_PORT_LIFECYCLE_RUNTIME_H

#include <stdbool.h>

void runtime_start(void);
bool runtime_run_entry(const char *module_name);
void runtime_stop(void);

#endif
