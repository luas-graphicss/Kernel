#include "virtqueue_peer.h"

#include "kernel/devices/virtio_queue.h"
#include "kernel/memory/endian.h"

#define DESCRIPTOR_BYTES 16u
#define DESCRIPTOR_LENGTH 8u
#define DESCRIPTOR_FLAGS 12u
#define DESCRIPTOR_NEXT 14u
#define RING_INDEX 2u
#define RING_ENTRIES 4u
#define AVAILABLE_ENTRY_BYTES 2u
#define USED_ENTRY_BYTES 8u
#define USED_ENTRY_LENGTH 4u

void virtqueue_peer_attach(struct virtqueue_peer *peer, uint64_t descriptors, uint64_t driver_ring,
                           uint64_t device_ring)
{
    *peer = (struct virtqueue_peer){
        .descriptors = (uint8_t *)(uintptr_t)descriptors,
        .driver_ring = (uint8_t *)(uintptr_t)driver_ring,
        .device_ring = (uint8_t *)(uintptr_t)device_ring,
    };
}

uint16_t virtqueue_peer_available(const struct virtqueue_peer *peer)
{
    return (uint16_t)little_endian_read(peer->driver_ring + RING_INDEX, 2);
}

uint16_t virtqueue_peer_head(const struct virtqueue_peer *peer, uint16_t position)
{
    const uint8_t *entry =
        peer->driver_ring + RING_ENTRIES + (position % VIRTIO_QUEUE_SIZE) * AVAILABLE_ENTRY_BYTES;

    return (uint16_t)little_endian_read(entry, 2);
}

uint16_t virtqueue_peer_newest_head(const struct virtqueue_peer *peer)
{
    return virtqueue_peer_head(peer, (uint16_t)(virtqueue_peer_available(peer) - 1u));
}

struct virtqueue_descriptor virtqueue_peer_descriptor(const struct virtqueue_peer *peer,
                                                      uint16_t index)
{
    const uint8_t *descriptor = peer->descriptors + index * DESCRIPTOR_BYTES;

    return (struct virtqueue_descriptor){
        .address = little_endian_read(descriptor, 8),
        .length = (uint32_t)little_endian_read(descriptor + DESCRIPTOR_LENGTH, 4),
        .flags = (uint16_t)little_endian_read(descriptor + DESCRIPTOR_FLAGS, 2),
        .next = (uint16_t)little_endian_read(descriptor + DESCRIPTOR_NEXT, 2),
    };
}

void virtqueue_peer_write_descriptor(struct virtqueue_peer *peer, uint16_t index,
                                     struct virtqueue_descriptor descriptor)
{
    uint8_t *target = peer->descriptors + index * DESCRIPTOR_BYTES;

    little_endian_write(target, 8, descriptor.address);
    little_endian_write(target + DESCRIPTOR_LENGTH, 4, descriptor.length);
    little_endian_write(target + DESCRIPTOR_FLAGS, 2, descriptor.flags);
    little_endian_write(target + DESCRIPTOR_NEXT, 2, descriptor.next);
}

void virtqueue_peer_complete(struct virtqueue_peer *peer, uint32_t head, uint32_t written)
{
    uint8_t *entry =
        peer->device_ring + RING_ENTRIES + (peer->used % VIRTIO_QUEUE_SIZE) * USED_ENTRY_BYTES;

    little_endian_write(entry, 4, head);
    little_endian_write(entry + USED_ENTRY_LENGTH, 4, written);
    virtqueue_peer_publish_used(peer, (uint16_t)(peer->used + 1u));
}

void virtqueue_peer_publish_used(struct virtqueue_peer *peer, uint16_t used)
{
    peer->used = used;
    little_endian_write(peer->device_ring + RING_INDEX, 2, used);
}
