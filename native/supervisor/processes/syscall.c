#include "kernel/processes/syscall.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/syscalls.h"
#include "kernel/diagnostics/console.h"

#define EXIT_STATUS_MASK 0xffffffffull

static int64_t debug_write(uint64_t address, uint64_t length, struct memory_range region)
{
    struct memory_range buffer = {.base = address, .length = length};

    if (length > SYSCALL_DEBUG_WRITE_MAX_BYTES) {
        return -KERNEL_ERROR_MESSAGE_TOO_LARGE;
    }
    if (length == 0) {
        return 0;
    }
    if (!memory_range_contains(region, buffer)) {
        return -KERNEL_ERROR_BAD_ADDRESS;
    }
    console_write((const char *)(uintptr_t)address, (size_t)length);
    return (int64_t)length;
}

struct syscall_result syscall_dispatch(const struct syscall_request *request,
                                       struct memory_range region)
{
    switch (request->number) {
    case SYSCALL_PROCESS_EXIT:
        return (struct syscall_result){
            .outcome = SYSCALL_EXIT,
            .value = (int64_t)(request->arguments[0] & EXIT_STATUS_MASK),
        };
    case SYSCALL_DEBUG_WRITE:
        return (struct syscall_result){
            .outcome = SYSCALL_RESUME,
            .value = debug_write(request->arguments[0], request->arguments[1], region),
        };
    default:
        return (struct syscall_result){
            .outcome = SYSCALL_RESUME,
            .value = -KERNEL_ERROR_UNSUPPORTED,
        };
    }
}
