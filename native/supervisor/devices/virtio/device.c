#include "kernel/devices/virtio_device.h"

#include <stddef.h>

#include "handshake.h"
#include "kernel/abi/errors.h"
#include "kernel/devices/virtio_mmio.h"
#include "kernel/memory/buffer_pins.h"

#define CONFIG_READ_ATTEMPTS 4u

static void unpin(struct virtio_pin *pin)
{
    for (uint32_t index = 0; index < pin->count; index++) {
        buffer_unpin(pin->buffers[index]);
    }
    pin->count = 0;
}

static void fail(struct virtio_device *device, const char *reason)
{
    device->state = DEVICE_STATE_FAILED;
    device->failure = reason;
}

static void complete(struct virtio_device *device, uint32_t queue, uint32_t chain,
                     uint32_t written)
{
    uint32_t position = (device->completion_head + device->completion_count) % VIRTIO_COMPLETIONS;

    device->completions[position] = (struct virtio_completion){
        .token = device->pins[queue][chain].token,
        .written = written,
        .queue = queue,
    };
    device->completion_count++;
    device->completions_of[queue]++;
    unpin(&device->pins[queue][chain]);
}

static bool drain(struct virtio_device *device, uint32_t queue)
{
    for (;;) {
        uint32_t chain = 0;
        uint32_t written = 0;
        enum virtio_used used = virtio_queue_take_used(&device->queues[queue], &chain, &written);

        if (used == VIRTIO_USED_EMPTY) {
            return true;
        }
        if (used == VIRTIO_USED_VIOLATION) {
            return false;
        }
        complete(device, queue, chain, written);
    }
}

static bool config_is_stable(const struct virtio_device *device, uint32_t offset, uint8_t *bytes,
                             uint32_t length)
{
    uint32_t generation = virtio_mmio_read(device->registers, VIRTIO_MMIO_CONFIG_GENERATION);

    for (uint32_t index = 0; index < length; index++) {
        bytes[index] = virtio_mmio_read_config(device->registers, offset + index);
    }
    return virtio_mmio_read(device->registers, VIRTIO_MMIO_CONFIG_GENERATION) == generation;
}

uint32_t virtio_device_identify(uintptr_t registers)
{
    if (virtio_mmio_read(registers, VIRTIO_MMIO_MAGIC_VALUE) != VIRTIO_MMIO_MAGIC ||
        virtio_mmio_read(registers, VIRTIO_MMIO_VERSION_VALUE) != VIRTIO_MMIO_VERSION) {
        return 0;
    }
    return virtio_mmio_read(registers, VIRTIO_MMIO_DEVICE_ID);
}

void virtio_device_attach(struct virtio_device *device, uintptr_t registers, void *queue_memory)
{
    *device = (struct virtio_device){
        .registers = registers,
        .model = virtio_device_identify(registers),
        .state = DEVICE_STATE_CLOSED,
    };
    virtio_device_add_queue(device, queue_memory);
}

bool virtio_device_add_queue(struct virtio_device *device, void *queue_memory)
{
    if (device->state != DEVICE_STATE_CLOSED || device->queue_capacity == DEVICE_QUEUES) {
        return false;
    }
    virtio_queue_init(&device->queues[device->queue_capacity], queue_memory);
    device->queue_capacity++;
    return true;
}

int64_t virtio_device_open(struct virtio_device *device, uint64_t wanted_features)
{
    int64_t status;

    if (device->state != DEVICE_STATE_CLOSED) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    status = virtio_device_reset(device);
    if (status != KERNEL_OK) {
        return status;
    }
    status = virtio_handshake_negotiate(device->registers, wanted_features, &device->features);
    if (status == KERNEL_OK) {
        status = virtio_handshake_attach_queues(device->registers, device->queues,
                                                device->queue_capacity, &device->queue_count);
    }
    if (status != KERNEL_OK) {
        return status;
    }
    virtio_handshake_start(device->registers);
    device->state = DEVICE_STATE_READY;
    return KERNEL_OK;
}

int64_t virtio_device_reset(struct virtio_device *device)
{
    if (device->state == DEVICE_STATE_QUARANTINED) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    if (!virtio_handshake_reset(device->registers)) {
        device->state = DEVICE_STATE_QUARANTINED;
        device->failure = "reset-not-acknowledged";
        return -KERNEL_ERROR_IO_ERROR;
    }
    for (uint32_t queue = 0; queue < device->queue_capacity; queue++) {
        for (uint32_t chain = 0; chain < DEVICE_REQUESTS; chain++) {
            unpin(&device->pins[queue][chain]);
        }
        virtio_queue_reset(&device->queues[queue]);
        device->completions_of[queue] = 0;
    }
    device->queue_count = 0;
    device->completion_head = 0;
    device->completion_count = 0;
    device->features = 0;
    device->failure = NULL;
    device->state = DEVICE_STATE_CLOSED;
    device->generation++;
    return KERNEL_OK;
}

int64_t virtio_device_submit(struct virtio_device *device, uint32_t queue,
                             const struct virtio_transfer *transfers, uint32_t count)
{
    struct virtio_segment segments[DEVICE_SEGMENTS] = {0};
    struct virtio_pin pin = {0};
    int64_t chain;

    if (device->state != DEVICE_STATE_READY) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    if (queue >= device->queue_count || count == 0 || count > DEVICE_SEGMENTS) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    if (virtio_queue_in_flight(&device->queues[queue]) + device->completions_of[queue] >=
        DEVICE_REQUESTS) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    for (uint32_t index = 0; index < count; index++) {
        if (!buffer_pin(transfers[index].buffer, transfers[index].offset, transfers[index].length,
                        &segments[index].address)) {
            unpin(&pin);
            return -KERNEL_ERROR_INVALID_ARGUMENT;
        }
        pin.buffers[pin.count] = transfers[index].buffer;
        pin.count++;
        segments[index].length = transfers[index].length;
        segments[index].device_writes = transfers[index].device_writes;
    }
    chain = virtio_queue_add(&device->queues[queue], segments, count);
    if (chain < 0) {
        unpin(&pin);
        return chain;
    }
    device->next_token++;
    pin.token = device->next_token;
    device->pins[queue][chain] = pin;
    virtio_mmio_write(device->registers, VIRTIO_MMIO_QUEUE_NOTIFY, queue);
    return (int64_t)pin.token;
}

void virtio_device_interrupt(struct virtio_device *device)
{
    uint32_t pending = virtio_mmio_read(device->registers, VIRTIO_MMIO_INTERRUPT_STATUS);

    virtio_mmio_write(device->registers, VIRTIO_MMIO_INTERRUPT_ACKNOWLEDGE, pending);
    if (device->state != DEVICE_STATE_READY) {
        return;
    }
    for (uint32_t queue = 0; queue < device->queue_count; queue++) {
        if (!drain(device, queue)) {
            fail(device, "used-ring-violation");
            return;
        }
    }
    if ((virtio_mmio_read(device->registers, VIRTIO_MMIO_STATUS) & VIRTIO_STATUS_NEEDS_RESET) != 0) {
        fail(device, "device-needs-reset");
    }
}

bool virtio_device_take_completion(struct virtio_device *device,
                                   struct virtio_completion *completion)
{
    if (device->completion_count == 0) {
        return false;
    }
    *completion = device->completions[device->completion_head];
    device->completion_head = (device->completion_head + 1u) % VIRTIO_COMPLETIONS;
    device->completion_count--;
    device->completions_of[completion->queue]--;
    return true;
}

int64_t virtio_device_read_config(const struct virtio_device *device, uint32_t offset,
                                  uint8_t *bytes, uint32_t length)
{
    if (device->state != DEVICE_STATE_READY) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    if (offset > DEVICE_CONFIG_BYTES || length > DEVICE_CONFIG_BYTES - offset) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    for (uint32_t attempt = 0; attempt < CONFIG_READ_ATTEMPTS; attempt++) {
        if (config_is_stable(device, offset, bytes, length)) {
            return (int64_t)length;
        }
    }
    return -KERNEL_ERROR_BAD_STATE;
}

uint32_t virtio_device_in_flight(const struct virtio_device *device)
{
    uint32_t in_flight = 0;

    for (uint32_t queue = 0; queue < device->queue_capacity; queue++) {
        in_flight += virtio_queue_in_flight(&device->queues[queue]);
    }
    return in_flight;
}
