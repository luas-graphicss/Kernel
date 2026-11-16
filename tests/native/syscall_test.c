#include <stdint.h>
#include <string.h>

#include "check.h"
#include "console_capture.h"
#include "kernel/abi/errors.h"
#include "kernel/abi/syscalls.h"
#include "kernel/processes/syscall.h"

#define PROCESS_BYTES 512u
#define UNKNOWN_SYSCALL 99u

static char process_memory[PROCESS_BYTES];

static struct memory_range process_region(void)
{
    return (struct memory_range){
        .base = (uint64_t)(uintptr_t)process_memory,
        .length = PROCESS_BYTES,
    };
}

static struct syscall_result call(uint64_t number, uint64_t first, uint64_t second)
{
    struct syscall_request request = {.number = number, .arguments = {first, second}};

    console_capture_reset();
    return syscall_dispatch(&request, process_region());
}

static struct syscall_result write_at(size_t offset, uint64_t length)
{
    return call(SYSCALL_DEBUG_WRITE, process_region().base + offset, length);
}

static void test_exit_keeps_the_low_status_bits(void)
{
    struct syscall_result result = call(SYSCALL_PROCESS_EXIT, 0x1234567800000007ull, 0);

    CHECK(result.outcome == SYSCALL_EXIT);
    CHECK(result.value == 7);
    CHECK(call(SYSCALL_PROCESS_EXIT, 0xffffffffull, 0).value == 0xffffffffll);
}

static void test_debug_write_copies_the_requested_bytes(void)
{
    struct syscall_result result;

    memcpy(process_memory + 16, "hello", 5);
    result = write_at(16, 5);
    CHECK(result.outcome == SYSCALL_RESUME);
    CHECK(result.value == 5);
    CHECK(console_capture_length() == 5);
    CHECK(memcmp(console_capture_bytes(), "hello", 5) == 0);
}

static void test_debug_write_accepts_the_boundaries(void)
{
    CHECK(write_at(0, 0).value == 0);
    CHECK(console_capture_length() == 0);
    CHECK(write_at(0, SYSCALL_DEBUG_WRITE_MAX_BYTES).value == SYSCALL_DEBUG_WRITE_MAX_BYTES);
    CHECK(write_at(PROCESS_BYTES - 1u, 1).value == 1);
    CHECK(call(SYSCALL_DEBUG_WRITE, 0, 0).value == 0);
}

static void test_debug_write_rejects_long_messages(void)
{
    CHECK(write_at(0, SYSCALL_DEBUG_WRITE_MAX_BYTES + 1u).value ==
          -KERNEL_ERROR_MESSAGE_TOO_LARGE);
    CHECK(console_capture_length() == 0);
    CHECK(write_at(0, UINT64_MAX).value == -KERNEL_ERROR_MESSAGE_TOO_LARGE);
}

static void test_debug_write_rejects_memory_outside_the_process(void)
{
    uint64_t base = process_region().base;

    CHECK(write_at(PROCESS_BYTES - 1u, 2).value == -KERNEL_ERROR_BAD_ADDRESS);
    CHECK(write_at(PROCESS_BYTES, 1).value == -KERNEL_ERROR_BAD_ADDRESS);
    CHECK(call(SYSCALL_DEBUG_WRITE, base - 1u, 2).value == -KERNEL_ERROR_BAD_ADDRESS);
    CHECK(call(SYSCALL_DEBUG_WRITE, 0, 1).value == -KERNEL_ERROR_BAD_ADDRESS);
    CHECK(call(SYSCALL_DEBUG_WRITE, UINT64_MAX, 2).value == -KERNEL_ERROR_BAD_ADDRESS);
    CHECK(console_capture_length() == 0);
}

static void test_unknown_syscall_is_unsupported(void)
{
    struct syscall_result result = call(UNKNOWN_SYSCALL, 0, 0);

    CHECK(result.outcome == SYSCALL_RESUME);
    CHECK(result.value == -KERNEL_ERROR_UNSUPPORTED);
    CHECK(call(UINT64_MAX, 0, 0).value == -KERNEL_ERROR_UNSUPPORTED);
}

int main(void)
{
    test_exit_keeps_the_low_status_bits();
    test_debug_write_copies_the_requested_bytes();
    test_debug_write_accepts_the_boundaries();
    test_debug_write_rejects_long_messages();
    test_debug_write_rejects_memory_outside_the_process();
    test_unknown_syscall_is_unsupported();
    return check_finish("syscall");
}
