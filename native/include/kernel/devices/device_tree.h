#ifndef KERNEL_DEVICES_DEVICE_TREE_H
#define KERNEL_DEVICES_DEVICE_TREE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "kernel/memory/range.h"

#define DEVICE_TREE_MAX_BYTES 65536u
#define DEVICE_TREE_MAX_DEPTH 8u
#define DEVICE_TREE_MAX_NAME_BYTES 255u
#define DEVICE_TREE_MAX_RESERVATIONS 16u
#define DEVICE_TREE_MAX_ARGUMENT_BYTES 255u

enum device_tree_status {
    DEVICE_TREE_OK,
    DEVICE_TREE_NULL,
    DEVICE_TREE_BAD_MAGIC,
    DEVICE_TREE_BAD_VERSION,
    DEVICE_TREE_TOO_LARGE,
    DEVICE_TREE_BAD_LAYOUT,
    DEVICE_TREE_BAD_STRUCTURE,
    DEVICE_TREE_TOO_DEEP,
    DEVICE_TREE_BAD_NAME,
    DEVICE_TREE_BAD_PROPERTY,
    DEVICE_TREE_TOO_MANY_RANGES,
    DEVICE_TREE_MISSING_MEMORY,
    DEVICE_TREE_MISSING_CONSOLE,
};

struct device_tree {
    const uint8_t *blob;
    uint32_t total_bytes;
    uint32_t reservations_offset;
    uint32_t structure_offset;
    uint32_t structure_bytes;
    uint32_t strings_offset;
    uint32_t strings_bytes;
};

struct boot_description {
    struct memory_range memory;
    struct memory_range console;
    struct memory_range reserved[DEVICE_TREE_MAX_RESERVATIONS];
    size_t reserved_count;
    bool has_boot_module;
    struct memory_range boot_module;
    const char *arguments;
    bool has_timebase;
    uint64_t timebase_frequency;
};

enum device_tree_status device_tree_open(const void *blob, size_t limit, struct device_tree *tree);
enum device_tree_status device_tree_describe_boot(const struct device_tree *tree,
                                                  struct boot_description *description);
const char *device_tree_status_name(enum device_tree_status status);

#endif
