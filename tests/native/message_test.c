#include <stdint.h>
#include <string.h>

#include "check.h"
#include "kernel/abi/errors.h"
#include "kernel/abi/ipc.h"
#include "kernel/abi/rights.h"
#include "kernel/events/event_queue.h"
#include "kernel/ipc/message.h"
#include "kernel/memory/endian.h"
#include "kernel/processes/spawn_request.h"
#include "kernel/timers/clock.h"

#define PAYLOAD_BYTES 16u
#define QEMU_FREQUENCY 10000000ull
#define EVENT_SLOTS 4u

static uint8_t message[IPC_MAX_MESSAGE_BYTES + 8u];
static uint8_t request_bytes[SPAWN_REQUEST_BYTES];

static void build_message(uint32_t payload_bytes)
{
    memset(message, 0, sizeof(message));
    little_endian_write(message + IPC_FIELD_VERSION, 2, IPC_VERSION);
    little_endian_write(message + IPC_FIELD_OPERATION, 4, 0x11223344u);
    little_endian_write(message + IPC_FIELD_PAYLOAD_BYTES, 4, payload_bytes);
    little_endian_write(message + IPC_FIELD_CORRELATION, 8, 0x0102030405060708ull);
}

static int64_t parse_with(uint32_t offset, uint32_t width, uint64_t value, uint64_t length)
{
    struct ipc_header header;

    build_message(PAYLOAD_BYTES);
    little_endian_write(message + offset, width, value);
    return ipc_message_parse(message, length, &header);
}

static void test_valid_message_is_described(void)
{
    struct ipc_header header = {0};

    build_message(PAYLOAD_BYTES);
    little_endian_write(message + IPC_FIELD_FLAGS, 2, IPC_FLAG_REPLY | IPC_FLAG_ERROR);
    CHECK(ipc_message_parse(message, IPC_HEADER_BYTES + PAYLOAD_BYTES, &header) == KERNEL_OK);
    CHECK(header.flags == (IPC_FLAG_REPLY | IPC_FLAG_ERROR));
    CHECK(header.operation == 0x11223344u);
    CHECK(header.payload_bytes == PAYLOAD_BYTES);
    CHECK(header.correlation == 0x0102030405060708ull);

    build_message(IPC_MAX_PAYLOAD_BYTES);
    CHECK(ipc_message_parse(message, IPC_MAX_MESSAGE_BYTES, &header) == KERNEL_OK);
    build_message(0);
    CHECK(ipc_message_parse(message, IPC_HEADER_BYTES, &header) == KERNEL_OK);
}

static void test_malformed_messages_fail_in_the_documented_order(void)
{
    uint64_t length = IPC_HEADER_BYTES + PAYLOAD_BYTES;

    CHECK(parse_with(IPC_FIELD_VERSION, 2, 2, IPC_HEADER_BYTES - 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_with(IPC_FIELD_VERSION, 2, 2, 0) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_with(IPC_FIELD_VERSION, 2, 2, length) == -KERNEL_ERROR_UNSUPPORTED);
    CHECK(parse_with(IPC_FIELD_VERSION, 2, 0, length) == -KERNEL_ERROR_UNSUPPORTED);
    CHECK(parse_with(IPC_FIELD_FLAGS, 2, 4, length) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_with(IPC_FIELD_FLAGS, 2, IPC_FLAG_ERROR, length) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_with(IPC_FIELD_FLAGS, 2, 0x8001u, length) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_with(IPC_FIELD_RESERVED, 4, 1, length) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_with(IPC_FIELD_PAYLOAD_BYTES, 4, IPC_MAX_PAYLOAD_BYTES + 1u, length) ==
          -KERNEL_ERROR_MESSAGE_TOO_LARGE);
    CHECK(parse_with(IPC_FIELD_PAYLOAD_BYTES, 4, UINT32_MAX, length) ==
          -KERNEL_ERROR_MESSAGE_TOO_LARGE);
    CHECK(parse_with(IPC_FIELD_PAYLOAD_BYTES, 4, PAYLOAD_BYTES + 1u, length) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_with(IPC_FIELD_PAYLOAD_BYTES, 4, PAYLOAD_BYTES, length + 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_with(IPC_FIELD_PAYLOAD_BYTES, 4, PAYLOAD_BYTES, length - 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
}

static void test_rejected_message_leaves_the_header_untouched(void)
{
    struct ipc_header header = {.operation = 7};

    build_message(PAYLOAD_BYTES);
    CHECK(ipc_message_parse(message, IPC_HEADER_BYTES, &header) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(header.operation == 7);
}

static void build_request(const char *name, uint32_t grants)
{
    size_t name_length = strlen(name);

    memset(request_bytes, 0, sizeof(request_bytes));
    little_endian_write(request_bytes + SPAWN_FIELD_VERSION, 4, SPAWN_REQUEST_VERSION);
    little_endian_write(request_bytes + SPAWN_FIELD_PRIORITY, 4, 2);
    little_endian_write(request_bytes + SPAWN_FIELD_HEAP_BYTES, 8, 0x20000);
    little_endian_write(request_bytes + SPAWN_FIELD_MEMORY_BYTES, 8, 0x4000);
    little_endian_write(request_bytes + SPAWN_FIELD_NAME_LENGTH, 4, name_length);
    little_endian_write(request_bytes + SPAWN_FIELD_ARGUMENT_LENGTH, 4, 3);
    little_endian_write(request_bytes + SPAWN_FIELD_GRANT_COUNT, 4, grants);
    for (uint32_t index = 0; index < grants; index++) {
        uint8_t *grant = request_bytes + SPAWN_FIELD_GRANTS + index * SPAWN_GRANT_BYTES;

        little_endian_write(grant + SPAWN_GRANT_HANDLE, 8, 0x1000000u + index);
        little_endian_write(grant + SPAWN_GRANT_RIGHTS, 8, RIGHT_SEND);
    }
    memcpy(request_bytes + SPAWN_FIELD_NAME, name, name_length);
    memcpy(request_bytes + SPAWN_FIELD_ARGUMENT, "abc", 3);
}

static int64_t parse_request_with(uint32_t offset, uint32_t width, uint64_t value)
{
    struct spawn_request request;

    build_request("services.echo", 2);
    little_endian_write(request_bytes + offset, width, value);
    return spawn_request_parse(request_bytes, &request);
}

static void test_spawn_request_is_read_field_by_field(void)
{
    struct spawn_request request = {0};

    build_request("services.echo", 2);
    CHECK(spawn_request_parse(request_bytes, &request) == KERNEL_OK);
    CHECK(request.priority == 2 && request.heap_bytes == 0x20000);
    CHECK(request.memory_bytes == 0x4000 && request.grant_count == 2);
    CHECK(request.name_length == 13 && strcmp(request.name, "services.echo") == 0);
    CHECK(request.argument_length == 3 && memcmp(request.argument, "abc", 3) == 0);
    CHECK(request.grants[1].handle == 0x1000001u && request.grants[1].rights == RIGHT_SEND);
}

static void test_spawn_request_rejects_inconsistent_fields(void)
{
    CHECK(parse_request_with(SPAWN_FIELD_VERSION, 4, 2) == -KERNEL_ERROR_UNSUPPORTED);
    CHECK(parse_request_with(SPAWN_FIELD_PRIORITY, 4, PROCESS_PRIORITY_LEVELS) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_HEAP_BYTES, 8, 0x20001) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_MEMORY_BYTES, 8, 1) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_NAME_LENGTH, 4, 0) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_NAME_LENGTH, 4, PROCESS_NAME_BYTES + 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_NAME_LENGTH, 4, 12) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_ARGUMENT_LENGTH, 4, PROCESS_ARGUMENT_BYTES + 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_ARGUMENT_LENGTH, 4, 2) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_GRANT_COUNT, 4, PROCESS_GRANTS + 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_GRANT_COUNT, 4, 1) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_RESERVED, 4, 1) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_GRANTS + SPAWN_GRANT_HANDLE, 8, 0) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_GRANTS + SPAWN_GRANT_RIGHTS, 8, 0) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_GRANTS + SPAWN_GRANT_RIGHTS, 8, RIGHTS_ALL + 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(parse_request_with(SPAWN_FIELD_GRANTS + SPAWN_GRANT_RIGHTS, 8, 1ull << 40) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
}

static void test_program_names_are_module_paths(void)
{
    CHECK(program_name_is_valid("init", 4));
    CHECK(program_name_is_valid("kernel_services.init.main", 25));
    CHECK(program_name_is_valid("a1.b2", 5));
    CHECK(!program_name_is_valid("", 0));
    CHECK(!program_name_is_valid(".init", 5));
    CHECK(!program_name_is_valid("init.", 5));
    CHECK(!program_name_is_valid("a..b", 4));
    CHECK(!program_name_is_valid("Init", 4));
    CHECK(!program_name_is_valid("a/b", 3));
    CHECK(!program_name_is_valid("a b", 3));
    CHECK(!program_name_is_valid("a\0b", 3));
}

static void test_clock_conversions_round_and_saturate(void)
{
    CHECK(clock_frequency_is_supported(QEMU_FREQUENCY));
    CHECK(clock_frequency_is_supported(CLOCK_MAX_FREQUENCY));
    CHECK(!clock_frequency_is_supported(0));
    CHECK(!clock_frequency_is_supported(CLOCK_MAX_FREQUENCY + 1u));

    CHECK(clock_ticks_to_nanoseconds(0, QEMU_FREQUENCY) == 0);
    CHECK(clock_ticks_to_nanoseconds(1, QEMU_FREQUENCY) == 100);
    CHECK(clock_ticks_to_nanoseconds(QEMU_FREQUENCY, QEMU_FREQUENCY) ==
          CLOCK_NANOSECONDS_PER_SECOND);
    CHECK(clock_ticks_to_nanoseconds(3, 2) == 1500000000ull);
    CHECK(clock_ticks_to_nanoseconds(1, 3) == 333333333ull);
    CHECK(clock_ticks_to_nanoseconds(UINT64_MAX, QEMU_FREQUENCY) == UINT64_MAX);
    CHECK(clock_ticks_to_nanoseconds(UINT64_MAX, CLOCK_MAX_FREQUENCY) ==
          UINT64_MAX / 10u);
    CHECK(clock_ticks_to_nanoseconds(UINT64_MAX, 1) == UINT64_MAX);

    CHECK(clock_nanoseconds_to_ticks(0, QEMU_FREQUENCY) == 0);
    CHECK(clock_nanoseconds_to_ticks(1, QEMU_FREQUENCY) == 1);
    CHECK(clock_nanoseconds_to_ticks(100, QEMU_FREQUENCY) == 1);
    CHECK(clock_nanoseconds_to_ticks(101, QEMU_FREQUENCY) == 2);
    CHECK(clock_nanoseconds_to_ticks(CLOCK_NANOSECONDS_PER_SECOND, QEMU_FREQUENCY) ==
          QEMU_FREQUENCY);
    CHECK(clock_nanoseconds_to_ticks(UINT64_MAX - 1u, QEMU_FREQUENCY) < UINT64_MAX);
    CHECK(clock_nanoseconds_to_ticks(UINT64_MAX - 1u, QEMU_FREQUENCY) >
          clock_nanoseconds_to_ticks(UINT64_MAX / 2u, QEMU_FREQUENCY));
    CHECK(clock_nanoseconds_to_ticks(UINT64_MAX, CLOCK_MAX_FREQUENCY) == UINT64_MAX);

    CHECK(clock_add(5, 7) == 12);
    CHECK(clock_add(UINT64_MAX - 1u, 1) == UINT64_MAX);
    CHECK(clock_add(UINT64_MAX - 1u, 2) == UINT64_MAX);
    CHECK(clock_add(UINT64_MAX, UINT64_MAX) == UINT64_MAX);
}

static void test_clock_round_trip_never_shortens_a_deadline(void)
{
    static const uint64_t samples[] = {1, 99, 100, 101, 12345678901ull, 1ull << 40,
                                       (1ull << 62) + 12345u};

    for (size_t index = 0; index < sizeof(samples) / sizeof(samples[0]); index++) {
        uint64_t ticks = clock_nanoseconds_to_ticks(samples[index], QEMU_FREQUENCY);

        CHECK(clock_ticks_to_nanoseconds(ticks, QEMU_FREQUENCY) >= samples[index]);
        CHECK(clock_ticks_to_nanoseconds(ticks - 1u, QEMU_FREQUENCY) < samples[index]);
    }
}

static void test_event_queue_keeps_order_and_counts_overflow(void)
{
    struct kernel_event slots[EVENT_SLOTS];
    struct kernel_event event = {0};
    struct event_queue queue;

    event_queue_init(&queue, slots, EVENT_SLOTS);
    CHECK(!event_queue_pop(&queue, &event));
    for (uint32_t index = 0; index < EVENT_SLOTS; index++) {
        CHECK(event_queue_push(&queue, (struct kernel_event){.kind = 1, .subject = index}));
    }
    CHECK(!event_queue_push(&queue, (struct kernel_event){.kind = 1, .subject = 99}));
    CHECK(!event_queue_push(&queue, (struct kernel_event){.kind = 1, .subject = 98}));
    CHECK(queue.dropped == 2);
    CHECK(event_queue_take_overflow(&queue));
    CHECK(!event_queue_take_overflow(&queue));
    for (uint32_t index = 0; index < EVENT_SLOTS; index++) {
        CHECK(event_queue_pop(&queue, &event) && event.subject == index);
    }
    CHECK(!event_queue_pop(&queue, &event));
    CHECK(event_queue_push(&queue, (struct kernel_event){.kind = 2, .subject = 5}));
    CHECK(event_queue_pop(&queue, &event) && event.kind == 2 && event.subject == 5);
    CHECK(queue.dropped == 2);
}

int main(void)
{
    test_valid_message_is_described();
    test_malformed_messages_fail_in_the_documented_order();
    test_rejected_message_leaves_the_header_untouched();
    test_spawn_request_is_read_field_by_field();
    test_spawn_request_rejects_inconsistent_fields();
    test_program_names_are_module_paths();
    test_clock_conversions_round_and_saturate();
    test_clock_round_trip_never_shortens_a_deadline();
    test_event_queue_keeps_order_and_counts_overflow();
    return check_finish("message");
}
