#ifndef KERNEL_DEVICES_DEVICE_INVENTORY_H
#define KERNEL_DEVICES_DEVICE_INVENTORY_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/abi/devices.h"
#include "kernel/devices/device_tree.h"
#include "kernel/memory/range.h"

#define INTERRUPT_SOURCE_LIMIT 1023u

struct interrupt_controller_description {
    bool present;
    struct memory_range registers;
    uint32_t sources;
    uint32_t supervisor_context;
};

struct device_description {
    struct memory_range registers;
    uint32_t interrupt;
};

struct device_inventory {
    struct interrupt_controller_description controller;
    bool has_serial;
    struct device_description serial;
    struct device_description transports[DEVICE_TRANSPORTS];
    uint32_t transport_count;
};

enum device_tree_status device_tree_describe_devices(const struct device_tree *tree,
                                                     struct device_inventory *inventory);

#endif
