#include "kernel/devices/virtio_queue.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/memory/string.h"

#define DESCRIPTOR_AREA 0x000u
#define DRIVER_AREA 0x200u
#define DEVICE_AREA 0x400u
#define DESCRIPTOR_BYTES 16u
#define DESCRIPTOR_LENGTH 8u
#define DESCRIPTOR_FLAGS 12u
#define DESCRIPTOR_NEXT 14u
#define DESCRIPTOR_CONTINUES 0x1u
#define DESCRIPTOR_DEVICE_WRITES 0x2u
#define RING_INDEX 2u
#define RING_ENTRIES 4u
#define AVAILABLE_ENTRY_BYTES 2u
#define USED_ENTRY_BYTES 8u
#define USED_ENTRY_LENGTH 4u

_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__, "virtqueue fields are little-endian");

static void store16(uint8_t *address, uint16_t value)
{
    *(volatile uint16_t *)(void *)address = value;
}

static void store32(uint8_t *address, uint32_t value)
{
    *(volatile uint32_t *)(void *)address = value;
}

static void store64(uint8_t *address, uint64_t value)
{
    *(volatile uint64_t *)(void *)address = value;
}

static uint16_t load16(const uint8_t *address)
{
    return *(const volatile uint16_t *)(const void *)address;
}

static uint32_t load32(const uint8_t *address)
{
    return *(const volatile uint32_t *)(const void *)address;
}

static bool order_is_valid(const struct virtio_segment *segments, uint32_t count)
{
    bool device_writes = false;

    for (uint32_t index = 0; index < count; index++) {
        if (segments[index].length == 0 || (device_writes && !segments[index].device_writes)) {
            return false;
        }
        device_writes = segments[index].device_writes;
    }
    return true;
}

static void write_descriptor(struct virtio_queue *queue, struct virtio_chain *chain,
                             uint32_t position, const struct virtio_segment *segment)
{
    uint8_t *descriptor = queue->memory + DESCRIPTOR_AREA + chain->indices[position] * DESCRIPTOR_BYTES;
    bool is_last = position + 1u == chain->descriptors;
    uint16_t flags = segment->device_writes ? DESCRIPTOR_DEVICE_WRITES : 0;

    store64(descriptor, segment->address);
    store32(descriptor + DESCRIPTOR_LENGTH, segment->length);
    store16(descriptor + DESCRIPTOR_FLAGS, is_last ? flags : (uint16_t)(flags | DESCRIPTOR_CONTINUES));
    store16(descriptor + DESCRIPTOR_NEXT, is_last ? 0 : chain->indices[position + 1u]);
    if (segment->device_writes) {
        chain->writable_bytes += segment->length;
    }
}

static void publish(struct virtio_queue *queue, uint16_t head)
{
    uint8_t *ring = queue->memory + DRIVER_AREA;

    store16(ring + RING_ENTRIES + (queue->available % VIRTIO_QUEUE_SIZE) * AVAILABLE_ENTRY_BYTES,
            head);
    __sync_synchronize();
    queue->available++;
    store16(ring + RING_INDEX, queue->available);
    __sync_synchronize();
}

static void release(struct virtio_queue *queue, struct virtio_chain *chain)
{
    queue->chain_of[chain->indices[0]] = VIRTIO_NO_CHAIN;
    for (uint32_t position = 0; position < chain->descriptors; position++) {
        queue->next_free[chain->indices[position]] = queue->free_head;
        queue->free_head = chain->indices[position];
    }
    queue->free_count = (uint16_t)(queue->free_count + chain->descriptors);
    chain->in_flight = false;
}

void virtio_queue_init(struct virtio_queue *queue, void *memory)
{
    queue->memory = memory;
    virtio_queue_reset(queue);
}

void virtio_queue_reset(struct virtio_queue *queue)
{
    memset(queue->memory, 0, VIRTIO_QUEUE_BYTES);
    for (uint16_t index = 0; index < VIRTIO_QUEUE_SIZE; index++) {
        queue->next_free[index] = (uint16_t)(index + 1u);
        queue->chain_of[index] = VIRTIO_NO_CHAIN;
    }
    for (uint32_t slot = 0; slot < DEVICE_REQUESTS; slot++) {
        queue->chains[slot] = (struct virtio_chain){0};
    }
    queue->free_head = 0;
    queue->free_count = VIRTIO_QUEUE_SIZE;
    queue->available = 0;
    queue->last_used = 0;
}

uint64_t virtio_queue_descriptor_area(const struct virtio_queue *queue)
{
    return (uint64_t)(uintptr_t)queue->memory + DESCRIPTOR_AREA;
}

uint64_t virtio_queue_driver_area(const struct virtio_queue *queue)
{
    return (uint64_t)(uintptr_t)queue->memory + DRIVER_AREA;
}

uint64_t virtio_queue_device_area(const struct virtio_queue *queue)
{
    return (uint64_t)(uintptr_t)queue->memory + DEVICE_AREA;
}

int64_t virtio_queue_add(struct virtio_queue *queue, const struct virtio_segment *segments,
                         uint32_t count)
{
    struct virtio_chain *chain;
    uint32_t slot = 0;

    if (count == 0 || count > DEVICE_SEGMENTS || !order_is_valid(segments, count)) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    while (slot < DEVICE_REQUESTS && queue->chains[slot].in_flight) {
        slot++;
    }
    if (slot == DEVICE_REQUESTS || queue->free_count < count) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    chain = &queue->chains[slot];
    *chain = (struct virtio_chain){.in_flight = true, .descriptors = (uint16_t)count};
    for (uint32_t position = 0; position < count; position++) {
        chain->indices[position] = queue->free_head;
        queue->free_head = queue->next_free[queue->free_head];
    }
    queue->free_count = (uint16_t)(queue->free_count - count);
    for (uint32_t position = 0; position < count; position++) {
        write_descriptor(queue, chain, position, &segments[position]);
    }
    queue->chain_of[chain->indices[0]] = (uint16_t)slot;
    publish(queue, chain->indices[0]);
    return slot;
}

enum virtio_used virtio_queue_take_used(struct virtio_queue *queue, uint32_t *chain,
                                        uint32_t *written)
{
    const uint8_t *ring = queue->memory + DEVICE_AREA;
    const uint8_t *entry =
        ring + RING_ENTRIES + (queue->last_used % VIRTIO_QUEUE_SIZE) * USED_ENTRY_BYTES;
    uint16_t reported;
    uint32_t head;
    uint32_t length;

    __sync_synchronize();
    reported = (uint16_t)(load16(ring + RING_INDEX) - queue->last_used);
    if (reported == 0) {
        return VIRTIO_USED_EMPTY;
    }
    if (reported > virtio_queue_in_flight(queue)) {
        return VIRTIO_USED_VIOLATION;
    }
    head = load32(entry);
    length = load32(entry + USED_ENTRY_LENGTH);
    if (head >= VIRTIO_QUEUE_SIZE || queue->chain_of[head] == VIRTIO_NO_CHAIN ||
        length > queue->chains[queue->chain_of[head]].writable_bytes) {
        return VIRTIO_USED_VIOLATION;
    }
    *chain = queue->chain_of[head];
    *written = length;
    release(queue, &queue->chains[*chain]);
    queue->last_used++;
    return VIRTIO_USED_COMPLETED;
}

uint32_t virtio_queue_in_flight(const struct virtio_queue *queue)
{
    uint32_t in_flight = 0;

    for (uint32_t slot = 0; slot < DEVICE_REQUESTS; slot++) {
        if (queue->chains[slot].in_flight) {
            in_flight++;
        }
    }
    return in_flight;
}
