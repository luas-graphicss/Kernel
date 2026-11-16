#ifndef KERNEL_DEVICES_VIRTIO_DEVICE_H
#define KERNEL_DEVICES_VIRTIO_DEVICE_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/abi/devices.h"
#include "kernel/devices/virtio_queue.h"

#define VIRTIO_COMPLETIONS (DEVICE_QUEUES * DEVICE_REQUESTS)

struct virtio_transfer {
    uint32_t buffer;
    uint32_t offset;
    uint32_t length;
    bool device_writes;
};

struct virtio_pin {
    uint32_t buffers[DEVICE_SEGMENTS];
    uint32_t count;
    uint64_t token;
};

struct virtio_completion {
    uint64_t token;
    uint32_t written;
    uint32_t queue;
};

struct virtio_device {
    uintptr_t registers;
    uint32_t model;
    uint32_t state;
    uint64_t features;
    uint64_t generation;
    uint64_t next_token;
    const char *failure;
    struct virtio_queue queues[DEVICE_QUEUES];
    uint32_t queue_capacity;
    uint32_t queue_count;
    struct virtio_pin pins[DEVICE_QUEUES][DEVICE_REQUESTS];
    struct virtio_completion completions[VIRTIO_COMPLETIONS];
    uint32_t completion_head;
    uint32_t completion_count;
    uint32_t completions_of[DEVICE_QUEUES];
};

uint32_t virtio_device_identify(uintptr_t registers);
void virtio_device_attach(struct virtio_device *device, uintptr_t registers, void *queue_memory);
bool virtio_device_add_queue(struct virtio_device *device, void *queue_memory);
int64_t virtio_device_open(struct virtio_device *device, uint64_t wanted_features);
int64_t virtio_device_reset(struct virtio_device *device);
int64_t virtio_device_submit(struct virtio_device *device, uint32_t queue,
                             const struct virtio_transfer *transfers, uint32_t count);
void virtio_device_interrupt(struct virtio_device *device);
bool virtio_device_take_completion(struct virtio_device *device,
                                   struct virtio_completion *completion);
int64_t virtio_device_read_config(const struct virtio_device *device, uint32_t offset,
                                  uint8_t *bytes, uint32_t length);
uint32_t virtio_device_in_flight(const struct virtio_device *device);

#endif
