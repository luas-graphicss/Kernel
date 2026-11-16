#ifndef KERNEL_SUPERVISOR_DEVICE_TREE_TOKENS_H
#define KERNEL_SUPERVISOR_DEVICE_TREE_TOKENS_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/devices/device_tree.h"

#define DEVICE_TREE_CELL_BYTES 4u

enum device_tree_token_kind {
    DEVICE_TREE_TOKEN_BEGIN_NODE = 1,
    DEVICE_TREE_TOKEN_END_NODE = 2,
    DEVICE_TREE_TOKEN_PROPERTY = 3,
    DEVICE_TREE_TOKEN_NOP = 4,
    DEVICE_TREE_TOKEN_END = 9,
};

struct device_tree_token {
    uint32_t kind;
    const char *name;
    const uint8_t *value;
    uint32_t value_bytes;
};

struct device_tree_cursor {
    const struct device_tree *tree;
    uint32_t offset;
};

uint32_t device_tree_read_be32(const uint8_t *bytes);
uint64_t device_tree_read_be64(const uint8_t *bytes);
enum device_tree_status device_tree_next_token(struct device_tree_cursor *cursor,
                                               struct device_tree_token *token);
enum device_tree_status device_tree_read_reservation(const struct device_tree *tree, uint32_t index,
                                                     struct memory_range *range, bool *is_last);

#endif
