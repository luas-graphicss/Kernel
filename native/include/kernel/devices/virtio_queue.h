#ifndef KERNEL_DEVICES_VIRTIO_QUEUE_H
#define KERNEL_DEVICES_VIRTIO_QUEUE_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/abi/devices.h"

#define VIRTIO_QUEUE_SIZE DEVICE_QUEUE_SIZE
#define VIRTIO_QUEUE_BYTES 4096u
#define VIRTIO_NO_CHAIN UINT16_MAX

struct virtio_segment {
    uint64_t address;
    uint32_t length;
    bool device_writes;
};

struct virtio_chain {
    bool in_flight;
    uint16_t descriptors;
    uint16_t indices[DEVICE_SEGMENTS];
    uint64_t writable_bytes;
};

struct virtio_queue {
    uint8_t *memory;
    uint16_t next_free[VIRTIO_QUEUE_SIZE];
    uint16_t chain_of[VIRTIO_QUEUE_SIZE];
    struct virtio_chain chains[DEVICE_REQUESTS];
    uint16_t free_head;
    uint16_t free_count;
    uint16_t available;
    uint16_t last_used;
};

enum virtio_used {
    VIRTIO_USED_EMPTY,
    VIRTIO_USED_COMPLETED,
    VIRTIO_USED_VIOLATION,
};

void virtio_queue_init(struct virtio_queue *queue, void *memory);
void virtio_queue_reset(struct virtio_queue *queue);
uint64_t virtio_queue_descriptor_area(const struct virtio_queue *queue);
uint64_t virtio_queue_driver_area(const struct virtio_queue *queue);
uint64_t virtio_queue_device_area(const struct virtio_queue *queue);
int64_t virtio_queue_add(struct virtio_queue *queue, const struct virtio_segment *segments,
                         uint32_t count);
enum virtio_used virtio_queue_take_used(struct virtio_queue *queue, uint32_t *chain,
                                        uint32_t *written);
uint32_t virtio_queue_in_flight(const struct virtio_queue *queue);

#endif
