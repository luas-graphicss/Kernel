#include "kernel/devices/device_tree.h"

#include "tokens.h"

#define HEADER_BYTES 40u
#define MAGIC 0xd00dfeedu
#define SUPPORTED_VERSION 17u
#define COMPATIBLE_VERSION 16u
#define RESERVATION_ALIGNMENT 8u
#define RESERVATION_ENTRY_BYTES 16u

#define HEADER_TOTAL_BYTES 4u
#define HEADER_STRUCTURE_OFFSET 8u
#define HEADER_STRINGS_OFFSET 12u
#define HEADER_RESERVATIONS_OFFSET 16u
#define HEADER_VERSION 20u
#define HEADER_COMPATIBLE_VERSION 24u
#define HEADER_STRINGS_BYTES 32u
#define HEADER_STRUCTURE_BYTES 36u

static enum device_tree_status check_layout(const struct device_tree *tree)
{
    uint64_t structure_end = (uint64_t)tree->structure_offset + tree->structure_bytes;
    uint64_t strings_end = (uint64_t)tree->strings_offset + tree->strings_bytes;

    if (tree->reservations_offset < HEADER_BYTES ||
        tree->reservations_offset % RESERVATION_ALIGNMENT != 0) {
        return DEVICE_TREE_BAD_LAYOUT;
    }
    if (tree->structure_offset % DEVICE_TREE_CELL_BYTES != 0 ||
        tree->structure_bytes % DEVICE_TREE_CELL_BYTES != 0 || tree->structure_bytes == 0) {
        return DEVICE_TREE_BAD_LAYOUT;
    }
    if ((uint64_t)tree->reservations_offset + RESERVATION_ENTRY_BYTES > tree->structure_offset) {
        return DEVICE_TREE_BAD_LAYOUT;
    }
    if (structure_end > tree->strings_offset || strings_end > tree->total_bytes) {
        return DEVICE_TREE_BAD_LAYOUT;
    }
    return DEVICE_TREE_OK;
}

static enum device_tree_status check_reservations(const struct device_tree *tree)
{
    for (uint32_t index = 0; index <= DEVICE_TREE_MAX_RESERVATIONS; index++) {
        struct memory_range range;
        bool is_last;
        enum device_tree_status status = device_tree_read_reservation(tree, index, &range, &is_last);
        if (status != DEVICE_TREE_OK || is_last) {
            return status;
        }
    }
    return DEVICE_TREE_TOO_MANY_RANGES;
}

static enum device_tree_status check_structure(const struct device_tree *tree)
{
    struct device_tree_cursor cursor = {.tree = tree};
    bool has_child[DEVICE_TREE_MAX_DEPTH] = {false};
    uint32_t depth = 0;
    bool root_closed = false;

    for (;;) {
        struct device_tree_token token;
        enum device_tree_status status = device_tree_next_token(&cursor, &token);
        if (status != DEVICE_TREE_OK) {
            return status;
        }

        switch (token.kind) {
        case DEVICE_TREE_TOKEN_BEGIN_NODE:
            if (root_closed || (depth == 0 && token.name[0] != '\0')) {
                return DEVICE_TREE_BAD_STRUCTURE;
            }
            if (depth == DEVICE_TREE_MAX_DEPTH) {
                return DEVICE_TREE_TOO_DEEP;
            }
            if (depth > 0) {
                has_child[depth - 1u] = true;
            }
            has_child[depth] = false;
            depth++;
            break;
        case DEVICE_TREE_TOKEN_PROPERTY:
            if (depth == 0 || has_child[depth - 1u]) {
                return DEVICE_TREE_BAD_STRUCTURE;
            }
            break;
        case DEVICE_TREE_TOKEN_END_NODE:
            if (depth == 0) {
                return DEVICE_TREE_BAD_STRUCTURE;
            }
            depth--;
            root_closed = depth == 0;
            break;
        case DEVICE_TREE_TOKEN_END:
            if (!root_closed || cursor.offset != tree->structure_bytes) {
                return DEVICE_TREE_BAD_STRUCTURE;
            }
            return DEVICE_TREE_OK;
        default:
            break;
        }
    }
}

enum device_tree_status device_tree_open(const void *blob, size_t limit, struct device_tree *tree)
{
    const uint8_t *bytes = blob;

    if (bytes == NULL) {
        return DEVICE_TREE_NULL;
    }
    if (limit < HEADER_BYTES) {
        return DEVICE_TREE_BAD_LAYOUT;
    }
    if (device_tree_read_be32(bytes) != MAGIC) {
        return DEVICE_TREE_BAD_MAGIC;
    }
    uint32_t total_bytes = device_tree_read_be32(bytes + HEADER_TOTAL_BYTES);
    if (total_bytes < HEADER_BYTES) {
        return DEVICE_TREE_BAD_LAYOUT;
    }
    if (total_bytes > limit) {
        return DEVICE_TREE_TOO_LARGE;
    }
    if (device_tree_read_be32(bytes + HEADER_VERSION) != SUPPORTED_VERSION ||
        device_tree_read_be32(bytes + HEADER_COMPATIBLE_VERSION) != COMPATIBLE_VERSION) {
        return DEVICE_TREE_BAD_VERSION;
    }

    struct device_tree candidate = {
        .blob = bytes,
        .total_bytes = total_bytes,
        .reservations_offset = device_tree_read_be32(bytes + HEADER_RESERVATIONS_OFFSET),
        .structure_offset = device_tree_read_be32(bytes + HEADER_STRUCTURE_OFFSET),
        .structure_bytes = device_tree_read_be32(bytes + HEADER_STRUCTURE_BYTES),
        .strings_offset = device_tree_read_be32(bytes + HEADER_STRINGS_OFFSET),
        .strings_bytes = device_tree_read_be32(bytes + HEADER_STRINGS_BYTES),
    };
    enum device_tree_status status = check_layout(&candidate);
    if (status == DEVICE_TREE_OK) {
        status = check_reservations(&candidate);
    }
    if (status == DEVICE_TREE_OK) {
        status = check_structure(&candidate);
    }
    if (status == DEVICE_TREE_OK) {
        *tree = candidate;
    }
    return status;
}

const char *device_tree_status_name(enum device_tree_status status)
{
    switch (status) {
    case DEVICE_TREE_OK:
        return "ok";
    case DEVICE_TREE_NULL:
        return "null-pointer";
    case DEVICE_TREE_BAD_MAGIC:
        return "bad-magic";
    case DEVICE_TREE_BAD_VERSION:
        return "bad-version";
    case DEVICE_TREE_TOO_LARGE:
        return "too-large";
    case DEVICE_TREE_BAD_LAYOUT:
        return "bad-layout";
    case DEVICE_TREE_BAD_STRUCTURE:
        return "bad-structure";
    case DEVICE_TREE_TOO_DEEP:
        return "too-deep";
    case DEVICE_TREE_BAD_NAME:
        return "bad-name";
    case DEVICE_TREE_BAD_PROPERTY:
        return "bad-property";
    case DEVICE_TREE_TOO_MANY_RANGES:
        return "too-many-ranges";
    case DEVICE_TREE_MISSING_MEMORY:
        return "missing-memory";
    case DEVICE_TREE_MISSING_CONSOLE:
        return "missing-console";
    }
    return "unknown";
}
