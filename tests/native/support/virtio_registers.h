#ifndef TESTS_NATIVE_SUPPORT_VIRTIO_REGISTERS_H
#define TESTS_NATIVE_SUPPORT_VIRTIO_REGISTERS_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/abi/devices.h"

#define VIRTIO_REGISTERS_STATUS_WRITES 8u
#define VIRTIO_REGISTERS_QUEUE_SIZE_MAX 1024u
#define VIRTIO_REGISTERS_QUEUE_INTERRUPT 0x1u

struct virtio_registers {
    uint32_t magic;
    uint32_t version;
    uint32_t model;
    uint64_t offered_features;
    uint64_t accepted_features;
    uint32_t offered_select;
    uint32_t accepted_select;
    uint32_t status;
    uint32_t status_writes[VIRTIO_REGISTERS_STATUS_WRITES];
    uint32_t status_write_count;
    uint32_t queue_select;
    uint32_t queue_size_max;
    uint32_t queue_size;
    uint32_t queue_ready;
    uint64_t descriptor_area;
    uint64_t driver_area;
    uint64_t device_area;
    uint32_t notifications;
    uint32_t interrupt_status;
    uint32_t config_generation;
    uint32_t config_changes;
    bool generation_was_read;
    bool refuses_features;
    bool ignores_reset;
    uint8_t config[DEVICE_CONFIG_BYTES];
};

void virtio_registers_init(struct virtio_registers *registers, uint32_t model, uint64_t features);
uintptr_t virtio_registers_address(struct virtio_registers *registers);
void virtio_registers_raise_interrupt(struct virtio_registers *registers);

#endif
