#include "kernel/processes/user_process.h"

#include <stddef.h>

#include "kernel/arch/trap_frame.h"
#include "kernel/arch/user_context.h"
#include "kernel/diagnostics/console.h"
#include "kernel/memory/string.h"
#include "kernel/processes/syscall.h"

#define STACK_ALIGNMENT 16ull
#define ENVIRONMENT_CALL_BYTES 4u

static struct trap_frame initial_frame(const struct user_image *image)
{
    struct trap_frame frame = {0};

    frame.program_counter = image->entry;
    frame.status = user_initial_status();
    frame.registers[REGISTER_STACK_POINTER] =
        (image->load_base + image->memory_bytes) & ~(STACK_ALIGNMENT - 1u);
    return frame;
}

static struct syscall_request read_request(const struct trap_frame *frame)
{
    struct syscall_request request = {.number = frame->registers[REGISTER_SYSCALL_NUMBER]};

    for (size_t index = 0; index < SYSCALL_ARGUMENTS; index++) {
        request.arguments[index] = frame->registers[REGISTER_ARGUMENT_FIRST + index];
    }
    return request;
}

static struct user_exit report_exit(uint32_t status)
{
    console_text("user: exit");
    console_field_decimal("status", status);
    console_end_line();
    return (struct user_exit){.reason = USER_EXIT_REQUESTED, .status = status};
}

static struct user_exit report_fault(const struct trap_frame *frame)
{
    console_text("user: fault");
    console_field_text("cause", trap_cause_name(frame->cause));
    console_field_hex("scause", frame->cause);
    console_field_hex("sepc", frame->program_counter);
    console_field_hex("stval", frame->value);
    console_end_line();
    return (struct user_exit){.reason = USER_EXIT_FAULT, .cause = frame->cause};
}

void user_image_load(const struct user_image *image, const uint8_t *module)
{
    uint8_t *destination = (uint8_t *)(uintptr_t)image->load_base;

    memcpy(destination, module, (size_t)image->file_bytes);
    memset(destination + image->file_bytes, 0, (size_t)(image->memory_bytes - image->file_bytes));
}

struct user_exit user_process_run(const struct user_image *image, struct memory_range region)
{
    struct trap_frame frame = initial_frame(image);

    for (;;) {
        struct syscall_request request;
        struct syscall_result result;

        user_context_enter(&frame);
        if (frame.cause != TRAP_CAUSE_USER_ENVIRONMENT_CALL) {
            return report_fault(&frame);
        }
        request = read_request(&frame);
        result = syscall_dispatch(&request, region);
        if (result.outcome == SYSCALL_EXIT) {
            return report_exit((uint32_t)result.value);
        }
        frame.registers[REGISTER_ARGUMENT_FIRST] = (uint64_t)result.value;
        frame.program_counter += ENVIRONMENT_CALL_BYTES;
    }
}
