#ifndef KERNEL_PORT_USER_PROCESS_CALLS_H
#define KERNEL_PORT_USER_PROCESS_CALLS_H

#include <stddef.h>

long process_debug_write(const char *bytes, size_t length);
_Noreturn void process_exit(unsigned int status);

#endif
