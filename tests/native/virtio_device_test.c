#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "check.h"
#include "kernel/abi/devices.h"
#include "kernel/abi/errors.h"
#include "kernel/devices/virtio_device.h"
#include "kernel/devices/virtio_mmio.h"
#include "kernel/memory/buffer_pins.h"
#include "pinned_buffers.h"
#include "virtio_registers.h"
#include "virtqueue_peer.h"

#define BLOCK_MODEL 2u
#define LEGACY_VERSION 1u
#define FEATURE_READ_ONLY (1ull << 5)
#define FEATURE_FLUSH (1ull << 9)
#define FEATURE_PACKED_RING (1ull << 34)
#define OFFERED_FEATURES                                                                          \
    (VIRTIO_FEATURE_VERSION_1 | FEATURE_READ_ONLY | FEATURE_FLUSH | FEATURE_PACKED_RING)
#define BUFFER_BASE 0x80200000ull
#define BUFFER_BYTES 4096u
#define SECTOR_BYTES 512u
#define CONFIG_READ_ATTEMPTS 4u

static _Alignas(VIRTIO_QUEUE_BYTES) uint8_t queue_memory[VIRTIO_QUEUE_BYTES];
static struct virtio_registers registers;
static struct virtio_device device;
static struct virtqueue_peer peer;
static uint32_t buffer;

static void attach_device(uint64_t offered_features)
{
    pinned_buffers_reset();
    buffer = pinned_buffers_add(BUFFER_BASE, BUFFER_BYTES);
    virtio_registers_init(&registers, BLOCK_MODEL, offered_features);
    virtio_device_attach(&device, virtio_registers_address(&registers), queue_memory);
}

static void open_device(void)
{
    attach_device(OFFERED_FEATURES);
    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == KERNEL_OK);
    virtqueue_peer_attach(&peer, registers.descriptor_area, registers.driver_area,
                          registers.device_area);
}

static int64_t submit(uint32_t offset, uint32_t length, bool device_writes)
{
    const struct virtio_transfer transfer = {buffer, offset, length, device_writes};

    return virtio_device_submit(&device, &transfer, 1);
}

static int64_t submit_read(void)
{
    return submit(0, SECTOR_BYTES, true);
}

static void interrupt(void)
{
    virtio_registers_raise_interrupt(&registers);
    virtio_device_interrupt(&device);
}

static bool device_failed_with(const char *reason)
{
    return device.state == DEVICE_STATE_FAILED && device.failure != NULL &&
           strcmp(device.failure, reason) == 0;
}

static void test_only_modern_transports_with_a_device_are_identified(void)
{
    uintptr_t address;

    attach_device(OFFERED_FEATURES);
    address = virtio_registers_address(&registers);
    CHECK(device.model == BLOCK_MODEL && device.state == DEVICE_STATE_CLOSED);
    CHECK(virtio_device_identify(address) == BLOCK_MODEL);
    registers.version = LEGACY_VERSION;
    CHECK(virtio_device_identify(address) == 0);
    registers.version = VIRTIO_MMIO_VERSION;
    registers.magic = 0;
    CHECK(virtio_device_identify(address) == 0);
    registers.magic = VIRTIO_MMIO_MAGIC;
    registers.model = 0;
    CHECK(virtio_device_identify(address) == 0);
}

static void test_open_negotiates_in_the_required_order(void)
{
    const uint32_t acknowledged = VIRTIO_STATUS_ACKNOWLEDGE;
    const uint32_t driver_known = acknowledged | VIRTIO_STATUS_DRIVER;
    const uint32_t features_accepted = driver_known | VIRTIO_STATUS_FEATURES_OK;
    const uint32_t expected[] = {
        0,
        acknowledged,
        driver_known,
        features_accepted,
        features_accepted | VIRTIO_STATUS_DRIVER_OK,
    };
    size_t steps = sizeof(expected) / sizeof(expected[0]);

    attach_device(OFFERED_FEATURES);
    CHECK(virtio_device_open(&device, FEATURE_FLUSH | FEATURE_PACKED_RING) == KERNEL_OK);
    CHECK(registers.status_write_count == steps);
    for (size_t step = 0; step < steps; step++) {
        CHECK(registers.status_writes[step] == expected[step]);
    }
    CHECK(device.features == (VIRTIO_FEATURE_VERSION_1 | FEATURE_FLUSH));
    CHECK(registers.accepted_features == device.features);
    CHECK(registers.queue_size == VIRTIO_QUEUE_SIZE && registers.queue_ready == 1);
    CHECK(registers.descriptor_area == virtio_queue_descriptor_area(&device.queue));
    CHECK(registers.driver_area == virtio_queue_driver_area(&device.queue));
    CHECK(registers.device_area == virtio_queue_device_area(&device.queue));
    CHECK(device.state == DEVICE_STATE_READY);
    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == -KERNEL_ERROR_BAD_STATE);
}

static void test_incompatible_devices_are_refused_and_marked_failed(void)
{
    attach_device(FEATURE_FLUSH);
    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == -KERNEL_ERROR_UNSUPPORTED);
    CHECK((registers.status & VIRTIO_STATUS_FAILED) != 0);
    CHECK((registers.status & VIRTIO_STATUS_DRIVER_OK) == 0);
    CHECK(device.state == DEVICE_STATE_CLOSED);

    attach_device(OFFERED_FEATURES);
    registers.queue_size_max = VIRTIO_QUEUE_SIZE - 1u;
    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == -KERNEL_ERROR_UNSUPPORTED);
    CHECK((registers.status & VIRTIO_STATUS_FAILED) != 0 && registers.queue_ready == 0);
    CHECK(device.state == DEVICE_STATE_CLOSED);

    attach_device(OFFERED_FEATURES);
    registers.refuses_features = true;
    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == -KERNEL_ERROR_UNSUPPORTED);
    CHECK((registers.status & VIRTIO_STATUS_FAILED) != 0 && registers.queue_ready == 0);
    CHECK(device.state == DEVICE_STATE_CLOSED);
    registers.refuses_features = false;
    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == KERNEL_OK);
    CHECK((registers.status & VIRTIO_STATUS_FAILED) == 0);
}

static void test_requests_pin_their_buffers_until_the_device_completes_them(void)
{
    struct virtio_completion completion = {0};
    struct virtqueue_descriptor descriptor;
    int64_t read_token;
    int64_t write_token;
    uint16_t read_head;
    uint16_t write_head;

    open_device();
    read_token = submit(SECTOR_BYTES, SECTOR_BYTES, true);
    read_head = virtqueue_peer_newest_head(&peer);
    write_token = submit(0, SECTOR_BYTES, false);
    write_head = virtqueue_peer_newest_head(&peer);
    CHECK(read_token == 1 && write_token == 2);
    CHECK(pinned_buffers_pins(buffer) == 2 && registers.notifications == 2);
    CHECK(virtio_device_in_flight(&device) == 2);
    descriptor = virtqueue_peer_descriptor(&peer, read_head);
    CHECK(descriptor.address == BUFFER_BASE + SECTOR_BYTES && descriptor.length == SECTOR_BYTES);
    CHECK(descriptor.flags == VIRTQUEUE_DESCRIPTOR_DEVICE_WRITES);

    virtqueue_peer_complete(&peer, write_head, 0);
    interrupt();
    CHECK(registers.interrupt_status == 0);
    CHECK(virtio_device_take_completion(&device, &completion));
    CHECK(completion.token == (uint64_t)write_token && completion.written == 0);
    CHECK(pinned_buffers_pins(buffer) == 1);
    CHECK(!virtio_device_take_completion(&device, &completion));

    virtqueue_peer_complete(&peer, read_head, SECTOR_BYTES);
    interrupt();
    CHECK(virtio_device_take_completion(&device, &completion));
    CHECK(completion.token == (uint64_t)read_token && completion.written == SECTOR_BYTES);
    CHECK(pinned_buffers_pins(buffer) == 0 && buffer_pinned_count() == 0);
}

static void test_requests_outside_their_buffers_are_refused_without_pins(void)
{
    open_device();
    const struct virtio_transfer unknown_buffer = {buffer + 1u, 0, SECTOR_BYTES, true};
    const struct virtio_transfer second_outside[] = {
        {buffer, 0, SECTOR_BYTES, false},
        {buffer, BUFFER_BYTES - 1u, 2, true},
    };
    const struct virtio_transfer readable_after_writable[] = {
        {buffer, 0, SECTOR_BYTES, true},
        {buffer, SECTOR_BYTES, SECTOR_BYTES, false},
    };

    CHECK(submit(BUFFER_BYTES, 1, true) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(submit(BUFFER_BYTES - 16u, 32, true) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(submit(0, BUFFER_BYTES + 1u, true) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(submit(UINT32_MAX, UINT32_MAX, true) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(submit(0, 0, false) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_device_submit(&device, &unknown_buffer, 1) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_device_submit(&device, second_outside, 0) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_device_submit(&device, second_outside, DEVICE_SEGMENTS + 1u) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_device_submit(&device, second_outside, 2) == -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_device_submit(&device, readable_after_writable, 2) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(pinned_buffers_pins(buffer) == 0 && registers.notifications == 0);
    CHECK(virtio_device_in_flight(&device) == 0 && virtqueue_peer_available(&peer) == 0);
    CHECK(submit(BUFFER_BYTES - SECTOR_BYTES, SECTOR_BYTES, true) == 1);
}

static void test_completions_not_yet_taken_count_against_the_request_limit(void)
{
    struct virtio_completion completion = {0};
    uint16_t heads[DEVICE_REQUESTS];

    open_device();
    for (uint32_t request = 0; request < DEVICE_REQUESTS; request++) {
        CHECK(submit_read() == (int64_t)request + 1);
        heads[request] = virtqueue_peer_newest_head(&peer);
    }
    CHECK(submit_read() == -KERNEL_ERROR_LIMIT_EXCEEDED);
    for (uint32_t request = 0; request < DEVICE_REQUESTS; request++) {
        virtqueue_peer_complete(&peer, heads[request], SECTOR_BYTES);
    }
    interrupt();
    CHECK(virtio_device_in_flight(&device) == 0 && pinned_buffers_pins(buffer) == 0);
    CHECK(submit_read() == -KERNEL_ERROR_LIMIT_EXCEEDED);
    CHECK(virtio_device_take_completion(&device, &completion) && completion.token == 1);
    CHECK(submit_read() == (int64_t)DEVICE_REQUESTS + 1);
}

static void test_a_used_ring_violation_stops_the_device_with_its_memory_pinned(void)
{
    struct virtio_completion completion = {0};

    open_device();
    CHECK(submit_read() == 1);
    virtqueue_peer_complete(&peer, virtqueue_peer_newest_head(&peer), SECTOR_BYTES + 1u);
    interrupt();
    CHECK(device_failed_with("used-ring-violation"));
    CHECK(!virtio_device_take_completion(&device, &completion));
    CHECK(pinned_buffers_pins(buffer) == 1);
    CHECK(submit_read() == -KERNEL_ERROR_BAD_STATE);

    CHECK(virtio_device_reset(&device) == KERNEL_OK);
    CHECK(device.state == DEVICE_STATE_CLOSED && device.failure == NULL);
    CHECK(pinned_buffers_pins(buffer) == 0);
}

static void test_a_duplicated_completion_stops_the_device_after_the_first(void)
{
    struct virtio_completion completion = {0};
    uint16_t first_head;

    open_device();
    CHECK(submit_read() == 1);
    first_head = virtqueue_peer_newest_head(&peer);
    CHECK(submit_read() == 2);
    virtqueue_peer_complete(&peer, first_head, 0);
    virtqueue_peer_complete(&peer, first_head, 0);
    interrupt();
    CHECK(device_failed_with("used-ring-violation"));
    CHECK(virtio_device_take_completion(&device, &completion) && completion.token == 1);
    CHECK(!virtio_device_take_completion(&device, &completion));
    CHECK(pinned_buffers_pins(buffer) == 1);
}

static void test_a_device_that_asks_for_reset_is_stopped_and_then_ignored(void)
{
    struct virtio_completion completion = {0};

    open_device();
    CHECK(submit_read() == 1);
    registers.status |= VIRTIO_STATUS_NEEDS_RESET;
    interrupt();
    CHECK(device_failed_with("device-needs-reset"));
    CHECK(pinned_buffers_pins(buffer) == 1);

    virtqueue_peer_complete(&peer, virtqueue_peer_newest_head(&peer), SECTOR_BYTES);
    interrupt();
    CHECK(registers.interrupt_status == 0);
    CHECK(!virtio_device_take_completion(&device, &completion));
    CHECK(pinned_buffers_pins(buffer) == 1);
}

static void test_a_reset_that_is_not_acknowledged_quarantines_the_device(void)
{
    open_device();
    CHECK(submit_read() == 1);
    registers.ignores_reset = true;
    CHECK(virtio_device_reset(&device) == -KERNEL_ERROR_IO_ERROR);
    CHECK(device.state == DEVICE_STATE_QUARANTINED);
    CHECK(device.failure != NULL && strcmp(device.failure, "reset-not-acknowledged") == 0);
    CHECK(pinned_buffers_pins(buffer) == 1);

    registers.ignores_reset = false;
    CHECK(virtio_device_reset(&device) == -KERNEL_ERROR_BAD_STATE);
    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == -KERNEL_ERROR_BAD_STATE);
    CHECK(submit_read() == -KERNEL_ERROR_BAD_STATE);
    CHECK(device.state == DEVICE_STATE_QUARANTINED && pinned_buffers_pins(buffer) == 1);
}

static void test_reset_drops_requests_and_starts_a_new_generation(void)
{
    struct virtio_completion completion = {0};
    uint64_t generation;

    open_device();
    generation = device.generation;
    CHECK(submit_read() == 1);
    virtqueue_peer_complete(&peer, virtqueue_peer_newest_head(&peer), SECTOR_BYTES);
    interrupt();
    CHECK(submit(SECTOR_BYTES, SECTOR_BYTES, false) == 2);
    CHECK(virtio_device_reset(&device) == KERNEL_OK);
    CHECK(device.state == DEVICE_STATE_CLOSED && device.features == 0);
    CHECK(device.generation == generation + 1u);
    CHECK(!virtio_device_take_completion(&device, &completion));
    CHECK(virtio_device_in_flight(&device) == 0 && pinned_buffers_pins(buffer) == 0);
    CHECK(submit_read() == -KERNEL_ERROR_BAD_STATE);

    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == KERNEL_OK);
    CHECK(device.generation == generation + 2u);
    CHECK(submit_read() == 3);
}

static void test_configuration_is_read_only_while_it_is_stable(void)
{
    uint8_t bytes[DEVICE_CONFIG_BYTES] = {0};

    attach_device(OFFERED_FEATURES);
    for (uint32_t index = 0; index < DEVICE_CONFIG_BYTES; index++) {
        registers.config[index] = (uint8_t)index;
    }
    CHECK(virtio_device_read_config(&device, 0, bytes, 8) == -KERNEL_ERROR_BAD_STATE);
    CHECK(virtio_device_open(&device, FEATURE_FLUSH) == KERNEL_OK);

    CHECK(virtio_device_read_config(&device, 8, bytes, 8) == 8);
    CHECK(bytes[0] == 8 && bytes[7] == 15);
    CHECK(virtio_device_read_config(&device, 0, bytes, DEVICE_CONFIG_BYTES) ==
          DEVICE_CONFIG_BYTES);
    CHECK(bytes[DEVICE_CONFIG_BYTES - 1u] == (uint8_t)(DEVICE_CONFIG_BYTES - 1u));
    CHECK(virtio_device_read_config(&device, DEVICE_CONFIG_BYTES, bytes, 0) == 0);
    CHECK(virtio_device_read_config(&device, DEVICE_CONFIG_BYTES + 1u, bytes, 0) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_device_read_config(&device, DEVICE_CONFIG_BYTES - 4u, bytes, 5) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);
    CHECK(virtio_device_read_config(&device, 1, bytes, UINT32_MAX) ==
          -KERNEL_ERROR_INVALID_ARGUMENT);

    registers.config_changes = CONFIG_READ_ATTEMPTS - 1u;
    CHECK(virtio_device_read_config(&device, 0, bytes, 8) == 8);
    registers.config_changes = CONFIG_READ_ATTEMPTS;
    CHECK(virtio_device_read_config(&device, 0, bytes, 8) == -KERNEL_ERROR_BAD_STATE);
}

int main(void)
{
    test_only_modern_transports_with_a_device_are_identified();
    test_open_negotiates_in_the_required_order();
    test_incompatible_devices_are_refused_and_marked_failed();
    test_requests_pin_their_buffers_until_the_device_completes_them();
    test_requests_outside_their_buffers_are_refused_without_pins();
    test_completions_not_yet_taken_count_against_the_request_limit();
    test_a_used_ring_violation_stops_the_device_with_its_memory_pinned();
    test_a_duplicated_completion_stops_the_device_after_the_first();
    test_a_device_that_asks_for_reset_is_stopped_and_then_ignored();
    test_a_reset_that_is_not_acknowledged_quarantines_the_device();
    test_reset_drops_requests_and_starts_a_new_generation();
    test_configuration_is_read_only_while_it_is_stable();
    return check_finish("virtio-device");
}
