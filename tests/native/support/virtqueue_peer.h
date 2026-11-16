#ifndef TESTS_NATIVE_SUPPORT_VIRTQUEUE_PEER_H
#define TESTS_NATIVE_SUPPORT_VIRTQUEUE_PEER_H

#include <stdint.h>

#define VIRTQUEUE_DESCRIPTOR_CONTINUES 0x1u
#define VIRTQUEUE_DESCRIPTOR_DEVICE_WRITES 0x2u

struct virtqueue_descriptor {
    uint64_t address;
    uint32_t length;
    uint16_t flags;
    uint16_t next;
};

struct virtqueue_peer {
    uint8_t *descriptors;
    uint8_t *driver_ring;
    uint8_t *device_ring;
    uint16_t used;
};

void virtqueue_peer_attach(struct virtqueue_peer *peer, uint64_t descriptors, uint64_t driver_ring,
                           uint64_t device_ring);
uint16_t virtqueue_peer_available(const struct virtqueue_peer *peer);
uint16_t virtqueue_peer_head(const struct virtqueue_peer *peer, uint16_t position);
uint16_t virtqueue_peer_newest_head(const struct virtqueue_peer *peer);
struct virtqueue_descriptor virtqueue_peer_descriptor(const struct virtqueue_peer *peer,
                                                      uint16_t index);
void virtqueue_peer_write_descriptor(struct virtqueue_peer *peer, uint16_t index,
                                     struct virtqueue_descriptor descriptor);
void virtqueue_peer_complete(struct virtqueue_peer *peer, uint32_t head, uint32_t written);
void virtqueue_peer_publish_used(struct virtqueue_peer *peer, uint16_t used);

#endif
