#ifndef KERNEL_DEVICES_DEVICE_REGISTRY_H
#define KERNEL_DEVICES_DEVICE_REGISTRY_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/abi/devices.h"
#include "kernel/devices/virtio_device.h"
#include "kernel/processes/process.h"
#include "kernel/startup/environment.h"

struct device_slot {
    bool present;
    uint32_t kind;
    uint32_t interrupt;
    uint64_t object;
    uint32_t holder;
    uint64_t holder_handle;
    uint32_t waiter;
    struct virtio_device virtio;
};

void device_registry_init(const struct boot_environment *environment);
struct device_slot *device_registry_slot(uint32_t index);
uint32_t device_registry_describe(uint8_t *entries);
int64_t device_registry_claim(const struct process *caller, uint32_t index);
int64_t device_registry_open(struct device_slot *slot, const struct process *caller,
                             uint64_t features);
int64_t device_registry_close(struct device_slot *slot);
bool device_registry_holds(const struct device_slot *slot, const struct process *caller);
void device_registry_await(struct device_slot *slot, struct process *caller, uint64_t deadline);
void device_registry_capability_released(uint32_t space, uint64_t object);
bool device_registry_has_waiters(void);
uint64_t device_registry_requests(void);
uint64_t device_registry_quarantined(void);

#endif
