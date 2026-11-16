#include "virtio_registers.h"

#include <stdlib.h>

#include "kernel/devices/virtio_mmio.h"

#define FEATURE_WORD_BITS 32u
#define FEATURE_WORD_MASK 0xffffffffull
#define FEATURE_WORDS 2u

static struct virtio_registers *model_of(uintptr_t device)
{
    return (struct virtio_registers *)device;
}

static uint32_t feature_word(uint64_t features, uint32_t word)
{
    if (word >= FEATURE_WORDS) {
        return 0;
    }
    return (uint32_t)((features >> (word * FEATURE_WORD_BITS)) & FEATURE_WORD_MASK);
}

static void store_word(uint64_t *target, uint32_t word, uint32_t value)
{
    uint32_t shift = word * FEATURE_WORD_BITS;

    if (word >= FEATURE_WORDS) {
        return;
    }
    *target = (*target & ~(FEATURE_WORD_MASK << shift)) | ((uint64_t)value << shift);
}

static void restart(struct virtio_registers *registers)
{
    registers->status = 0;
    registers->accepted_features = 0;
    registers->queue_size = 0;
    registers->queue_ready = 0;
    registers->interrupt_status = 0;
}

static void write_status(struct virtio_registers *registers, uint32_t value)
{
    if (registers->status_write_count < VIRTIO_REGISTERS_STATUS_WRITES) {
        registers->status_writes[registers->status_write_count] = value;
    }
    registers->status_write_count++;
    if (value == 0) {
        if (!registers->ignores_reset) {
            restart(registers);
        }
        return;
    }
    registers->status = value;
    if (registers->refuses_features) {
        registers->status &= ~VIRTIO_STATUS_FEATURES_OK;
    }
}

void virtio_registers_init(struct virtio_registers *registers, uint32_t model, uint64_t features)
{
    *registers = (struct virtio_registers){
        .magic = VIRTIO_MMIO_MAGIC,
        .version = VIRTIO_MMIO_VERSION,
        .model = model,
        .offered_features = features,
        .queue_size_max = VIRTIO_REGISTERS_QUEUE_SIZE_MAX,
    };
}

uintptr_t virtio_registers_address(struct virtio_registers *registers)
{
    return (uintptr_t)registers;
}

void virtio_registers_raise_interrupt(struct virtio_registers *registers)
{
    registers->interrupt_status |= VIRTIO_REGISTERS_QUEUE_INTERRUPT;
}

uint32_t virtio_mmio_read(uintptr_t device, uint32_t offset)
{
    struct virtio_registers *registers = model_of(device);

    switch (offset) {
    case VIRTIO_MMIO_MAGIC_VALUE:
        return registers->magic;
    case VIRTIO_MMIO_VERSION_VALUE:
        return registers->version;
    case VIRTIO_MMIO_DEVICE_ID:
        return registers->model;
    case VIRTIO_MMIO_DEVICE_FEATURES:
        return feature_word(registers->offered_features, registers->offered_select);
    case VIRTIO_MMIO_QUEUE_SIZE_MAX:
        return registers->queue_select == 0 ? registers->queue_size_max : 0;
    case VIRTIO_MMIO_QUEUE_READY:
        return registers->queue_ready;
    case VIRTIO_MMIO_INTERRUPT_STATUS:
        return registers->interrupt_status;
    case VIRTIO_MMIO_STATUS:
        return registers->status;
    case VIRTIO_MMIO_CONFIG_GENERATION:
        registers->generation_was_read = true;
        return registers->config_generation;
    default:
        return 0;
    }
}

void virtio_mmio_write(uintptr_t device, uint32_t offset, uint32_t value)
{
    struct virtio_registers *registers = model_of(device);

    switch (offset) {
    case VIRTIO_MMIO_DEVICE_FEATURES_SELECT:
        registers->offered_select = value;
        break;
    case VIRTIO_MMIO_DRIVER_FEATURES_SELECT:
        registers->accepted_select = value;
        break;
    case VIRTIO_MMIO_DRIVER_FEATURES:
        store_word(&registers->accepted_features, registers->accepted_select, value);
        break;
    case VIRTIO_MMIO_QUEUE_SELECT:
        registers->queue_select = value;
        break;
    case VIRTIO_MMIO_QUEUE_SIZE:
        registers->queue_size = value;
        break;
    case VIRTIO_MMIO_QUEUE_READY:
        registers->queue_ready = value;
        break;
    case VIRTIO_MMIO_QUEUE_NOTIFY:
        registers->notifications++;
        break;
    case VIRTIO_MMIO_INTERRUPT_ACKNOWLEDGE:
        registers->interrupt_status &= ~value;
        break;
    case VIRTIO_MMIO_STATUS:
        write_status(registers, value);
        break;
    case VIRTIO_MMIO_QUEUE_DESCRIPTOR_LOW:
        store_word(&registers->descriptor_area, 0, value);
        break;
    case VIRTIO_MMIO_QUEUE_DESCRIPTOR_HIGH:
        store_word(&registers->descriptor_area, 1, value);
        break;
    case VIRTIO_MMIO_QUEUE_DRIVER_LOW:
        store_word(&registers->driver_area, 0, value);
        break;
    case VIRTIO_MMIO_QUEUE_DRIVER_HIGH:
        store_word(&registers->driver_area, 1, value);
        break;
    case VIRTIO_MMIO_QUEUE_DEVICE_LOW:
        store_word(&registers->device_area, 0, value);
        break;
    case VIRTIO_MMIO_QUEUE_DEVICE_HIGH:
        store_word(&registers->device_area, 1, value);
        break;
    default:
        break;
    }
}

uint8_t virtio_mmio_read_config(uintptr_t device, uint32_t offset)
{
    struct virtio_registers *registers = model_of(device);

    if (offset >= DEVICE_CONFIG_BYTES) {
        abort();
    }
    if (registers->generation_was_read && registers->config_changes > 0) {
        registers->config_changes--;
        registers->config_generation++;
    }
    registers->generation_was_read = false;
    return registers->config[offset];
}
