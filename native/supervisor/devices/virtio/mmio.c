#include "kernel/devices/virtio_mmio.h"

uint32_t virtio_mmio_read(uintptr_t device, uint32_t offset)
{
    return *(const volatile uint32_t *)(device + offset);
}

void virtio_mmio_write(uintptr_t device, uint32_t offset, uint32_t value)
{
    *(volatile uint32_t *)(device + offset) = value;
}

uint8_t virtio_mmio_read_config(uintptr_t device, uint32_t offset)
{
    return *(const volatile uint8_t *)(device + VIRTIO_MMIO_CONFIG + offset);
}
