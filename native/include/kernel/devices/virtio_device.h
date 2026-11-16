#ifndef KERNEL_DEVICES_VIRTIO_DEVICE_H
#define KERNEL_DEVICES_VIRTIO_DEVICE_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/abi/devices.h"
#include "kernel/devices/virtio_queue.h"

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
};

struct virtio_device {
    uintptr_t registers;
    uint32_t model;
    uint32_t state;
    uint64_t features;
    uint64_t generation;
    uint64_t next_token;
    const char *failure;
    struct virtio_queue queue;
    struct virtio_pin pins[DEVICE_REQUESTS];
    struct virtio_completion completions[DEVICE_REQUESTS];
    uint32_t completion_head;
    uint32_t completion_count;
};

uint32_t virtio_device_identify(uintptr_t registers);
void virtio_device_attach(struct virtio_device *device, uintptr_t registers, void *queue_memory);
int64_t virtio_device_open(struct virtio_device *device, uint64_t wanted_features);
int64_t virtio_device_reset(struct virtio_device *device);
int64_t virtio_device_submit(struct virtio_device *device, const struct virtio_transfer *transfers,
                             uint32_t count);
void virtio_device_interrupt(struct virtio_device *device);
bool virtio_device_take_completion(struct virtio_device *device,
                                   struct virtio_completion *completion);
int64_t virtio_device_read_config(const struct virtio_device *device, uint32_t offset,
                                  uint8_t *bytes, uint32_t length);
uint32_t virtio_device_in_flight(const struct virtio_device *device);

#endif
