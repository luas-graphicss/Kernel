#ifndef KERNEL_MEMORY_STRING_H
#define KERNEL_MEMORY_STRING_H

#include <stddef.h>

void *memcpy(void *restrict destination, const void *restrict source, size_t length);
void *memset(void *destination, int value, size_t length);
size_t strlen(const char *text);

#endif
