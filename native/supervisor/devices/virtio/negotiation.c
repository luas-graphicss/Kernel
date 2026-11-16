#include "handshake.h"

#include "kernel/abi/devices.h"
#include "kernel/abi/errors.h"
#include "kernel/devices/virtio_mmio.h"

#define FEATURE_WORD_BITS 32u
#define FEATURE_WORD_MASK 0xffffffffull
#define RESET_POLL_LIMIT 100000u
#define FIRST_QUEUE 0u

static void add_status(uintptr_t device, uint32_t bits)
{
    virtio_mmio_write(device, VIRTIO_MMIO_STATUS,
                      virtio_mmio_read(device, VIRTIO_MMIO_STATUS) | bits);
}

static int64_t refuse(uintptr_t device)
{
    add_status(device, VIRTIO_STATUS_FAILED);
    return -KERNEL_ERROR_UNSUPPORTED;
}

static uint64_t offered_features(uintptr_t device)
{
    uint64_t features;

    virtio_mmio_write(device, VIRTIO_MMIO_DEVICE_FEATURES_SELECT, 1);
    features = (uint64_t)virtio_mmio_read(device, VIRTIO_MMIO_DEVICE_FEATURES) << FEATURE_WORD_BITS;
    virtio_mmio_write(device, VIRTIO_MMIO_DEVICE_FEATURES_SELECT, 0);
    return features | virtio_mmio_read(device, VIRTIO_MMIO_DEVICE_FEATURES);
}

static void accept_features(uintptr_t device, uint64_t features)
{
    virtio_mmio_write(device, VIRTIO_MMIO_DRIVER_FEATURES_SELECT, 0);
    virtio_mmio_write(device, VIRTIO_MMIO_DRIVER_FEATURES, (uint32_t)(features & FEATURE_WORD_MASK));
    virtio_mmio_write(device, VIRTIO_MMIO_DRIVER_FEATURES_SELECT, 1);
    virtio_mmio_write(device, VIRTIO_MMIO_DRIVER_FEATURES, (uint32_t)(features >> FEATURE_WORD_BITS));
}

static void write_area(uintptr_t device, uint32_t low_register, uint64_t address)
{
    virtio_mmio_write(device, low_register, (uint32_t)(address & FEATURE_WORD_MASK));
    virtio_mmio_write(device, low_register + sizeof(uint32_t),
                      (uint32_t)(address >> FEATURE_WORD_BITS));
}

bool virtio_handshake_reset(uintptr_t device)
{
    virtio_mmio_write(device, VIRTIO_MMIO_STATUS, 0);
    for (uint32_t poll = 0; poll < RESET_POLL_LIMIT; poll++) {
        if (virtio_mmio_read(device, VIRTIO_MMIO_STATUS) == 0) {
            return true;
        }
    }
    return false;
}

int64_t virtio_handshake_negotiate(uintptr_t device, uint64_t wanted, uint64_t *accepted)
{
    uint64_t offered;

    add_status(device, VIRTIO_STATUS_ACKNOWLEDGE);
    add_status(device, VIRTIO_STATUS_DRIVER);
    offered = offered_features(device);
    if ((offered & VIRTIO_FEATURE_VERSION_1) == 0) {
        return refuse(device);
    }
    *accepted = (offered & wanted & DEVICE_FEATURE_MASK) | VIRTIO_FEATURE_VERSION_1;
    accept_features(device, *accepted);
    add_status(device, VIRTIO_STATUS_FEATURES_OK);
    if ((virtio_mmio_read(device, VIRTIO_MMIO_STATUS) & VIRTIO_STATUS_FEATURES_OK) == 0) {
        return refuse(device);
    }
    return KERNEL_OK;
}

static bool attach_queue(uintptr_t device, const struct virtio_queue *queue)
{
    if (virtio_mmio_read(device, VIRTIO_MMIO_QUEUE_READY) != 0 ||
        virtio_mmio_read(device, VIRTIO_MMIO_QUEUE_SIZE_MAX) < VIRTIO_QUEUE_SIZE) {
        return false;
    }
    virtio_mmio_write(device, VIRTIO_MMIO_QUEUE_SIZE, VIRTIO_QUEUE_SIZE);
    write_area(device, VIRTIO_MMIO_QUEUE_DESCRIPTOR_LOW, virtio_queue_descriptor_area(queue));
    write_area(device, VIRTIO_MMIO_QUEUE_DRIVER_LOW, virtio_queue_driver_area(queue));
    write_area(device, VIRTIO_MMIO_QUEUE_DEVICE_LOW, virtio_queue_device_area(queue));
    virtio_mmio_write(device, VIRTIO_MMIO_QUEUE_READY, 1);
    return true;
}

int64_t virtio_handshake_attach_queues(uintptr_t device, const struct virtio_queue *queues,
                                       uint32_t capacity, uint32_t *attached)
{
    *attached = 0;
    for (uint32_t index = 0; index < capacity; index++) {
        virtio_mmio_write(device, VIRTIO_MMIO_QUEUE_SELECT, index);
        if (index != FIRST_QUEUE && virtio_mmio_read(device, VIRTIO_MMIO_QUEUE_SIZE_MAX) == 0) {
            break;
        }
        if (!attach_queue(device, &queues[index])) {
            *attached = 0;
            return refuse(device);
        }
        (*attached)++;
    }
    return KERNEL_OK;
}

void virtio_handshake_start(uintptr_t device)
{
    add_status(device, VIRTIO_STATUS_DRIVER_OK);
}
