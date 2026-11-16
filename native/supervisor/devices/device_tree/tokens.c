#include "tokens.h"

#include <stddef.h>

static uint32_t align_to_cell(uint32_t value)
{
    return (value + (DEVICE_TREE_CELL_BYTES - 1u)) & ~(DEVICE_TREE_CELL_BYTES - 1u);
}

static bool text_length(const uint8_t *text, uint32_t available, uint32_t *length)
{
    uint32_t scanned = available;
    if (scanned > DEVICE_TREE_MAX_NAME_BYTES + 1u) {
        scanned = DEVICE_TREE_MAX_NAME_BYTES + 1u;
    }
    for (uint32_t index = 0; index < scanned; index++) {
        if (text[index] == 0) {
            *length = index;
            return true;
        }
    }
    return false;
}

static enum device_tree_status read_node_name(struct device_tree_cursor *cursor,
                                              struct device_tree_token *token)
{
    const struct device_tree *tree = cursor->tree;
    const uint8_t *name = tree->blob + tree->structure_offset + cursor->offset;
    uint32_t remaining = tree->structure_bytes - cursor->offset;
    uint32_t length;

    if (!text_length(name, remaining, &length)) {
        return DEVICE_TREE_BAD_NAME;
    }
    uint32_t consumed = align_to_cell(length + 1u);
    if (consumed > remaining) {
        return DEVICE_TREE_BAD_STRUCTURE;
    }
    token->name = (const char *)name;
    cursor->offset += consumed;
    return DEVICE_TREE_OK;
}

static enum device_tree_status read_property(struct device_tree_cursor *cursor,
                                             struct device_tree_token *token)
{
    const struct device_tree *tree = cursor->tree;
    const uint8_t *header = tree->blob + tree->structure_offset + cursor->offset;
    uint32_t remaining = tree->structure_bytes - cursor->offset;
    uint32_t header_bytes = 2u * DEVICE_TREE_CELL_BYTES;

    if (remaining < header_bytes) {
        return DEVICE_TREE_BAD_STRUCTURE;
    }
    uint32_t value_bytes = device_tree_read_be32(header);
    uint32_t name_offset = device_tree_read_be32(header + DEVICE_TREE_CELL_BYTES);
    remaining -= header_bytes;
    if (value_bytes > remaining || align_to_cell(value_bytes) > remaining) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    if (name_offset >= tree->strings_bytes) {
        return DEVICE_TREE_BAD_NAME;
    }

    const uint8_t *name = tree->blob + tree->strings_offset + name_offset;
    uint32_t name_length;
    if (!text_length(name, tree->strings_bytes - name_offset, &name_length)) {
        return DEVICE_TREE_BAD_NAME;
    }
    token->name = (const char *)name;
    token->value = header + header_bytes;
    token->value_bytes = value_bytes;
    cursor->offset += header_bytes + align_to_cell(value_bytes);
    return DEVICE_TREE_OK;
}

uint32_t device_tree_read_be32(const uint8_t *bytes)
{
    return ((uint32_t)bytes[0] << 24) | ((uint32_t)bytes[1] << 16) | ((uint32_t)bytes[2] << 8) |
           (uint32_t)bytes[3];
}

uint64_t device_tree_read_be64(const uint8_t *bytes)
{
    return ((uint64_t)device_tree_read_be32(bytes) << 32) |
           device_tree_read_be32(bytes + DEVICE_TREE_CELL_BYTES);
}

enum device_tree_status device_tree_next_token(struct device_tree_cursor *cursor,
                                               struct device_tree_token *token)
{
    const struct device_tree *tree = cursor->tree;

    if (tree->structure_bytes - cursor->offset < DEVICE_TREE_CELL_BYTES) {
        return DEVICE_TREE_BAD_STRUCTURE;
    }
    *token = (struct device_tree_token){
        .kind = device_tree_read_be32(tree->blob + tree->structure_offset + cursor->offset),
    };
    cursor->offset += DEVICE_TREE_CELL_BYTES;

    switch (token->kind) {
    case DEVICE_TREE_TOKEN_BEGIN_NODE:
        return read_node_name(cursor, token);
    case DEVICE_TREE_TOKEN_PROPERTY:
        return read_property(cursor, token);
    case DEVICE_TREE_TOKEN_END_NODE:
    case DEVICE_TREE_TOKEN_NOP:
    case DEVICE_TREE_TOKEN_END:
        return DEVICE_TREE_OK;
    default:
        return DEVICE_TREE_BAD_STRUCTURE;
    }
}

enum device_tree_status device_tree_read_reservation(const struct device_tree *tree, uint32_t index,
                                                     struct memory_range *range, bool *is_last)
{
    uint64_t entry_bytes = 2u * sizeof(uint64_t);
    uint64_t offset = (uint64_t)tree->reservations_offset + (uint64_t)index * entry_bytes;

    if (offset + entry_bytes > tree->structure_offset) {
        return DEVICE_TREE_BAD_LAYOUT;
    }
    range->base = device_tree_read_be64(tree->blob + offset);
    range->length = device_tree_read_be64(tree->blob + offset + sizeof(uint64_t));
    *is_last = range->base == 0 && range->length == 0;
    return DEVICE_TREE_OK;
}
