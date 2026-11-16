#ifndef KERNEL_ARCH_SBI_H
#define KERNEL_ARCH_SBI_H

#include <stddef.h>
#include <stdint.h>

struct sbi_result {
    long error;
    long value;
};

struct sbi_result sbi_call(unsigned long extension, unsigned long function, unsigned long first,
                           unsigned long second, unsigned long third);
size_t sbi_console_write(const char *bytes, size_t length);
void sbi_timer_set(uint64_t deadline);
_Noreturn void sbi_shutdown(void);
_Noreturn void cpu_wait_forever(void);

#endif
