#include "properties.h"

bool device_tree_text_equals(const char *left, const char *right)
{
    while (*left != '\0' && *left == *right) {
        left++;
        right++;
    }
    return *left == *right;
}

bool device_tree_value_is_text(const uint8_t *bytes, uint32_t length, const char *text)
{
    uint32_t index = 0;

    while (index < length && text[index] != '\0') {
        if (bytes[index] != (uint8_t)text[index]) {
            return false;
        }
        index++;
    }
    return index + 1u == length && text[index] == '\0' && bytes[index] == 0;
}

bool device_tree_list_has_text(const struct device_tree_token *property, const char *text)
{
    uint32_t start = 0;

    while (start < property->value_bytes) {
        uint32_t end = start;

        while (end < property->value_bytes && property->value[end] != 0) {
            end++;
        }
        if (end == property->value_bytes) {
            return false;
        }
        if (device_tree_value_is_text(property->value + start, end - start + 1u, text)) {
            return true;
        }
        start = end + 1u;
    }
    return false;
}

bool device_tree_read_cells(const uint8_t *bytes, uint32_t cells, uint64_t *value)
{
    if (cells == 1u) {
        *value = device_tree_read_be32(bytes);
        return true;
    }
    if (cells == 2u) {
        *value = device_tree_read_be64(bytes);
        return true;
    }
    return false;
}

uint32_t device_tree_range_bytes(uint32_t address_cells, uint32_t size_cells)
{
    return (address_cells + size_cells) * DEVICE_TREE_CELL_BYTES;
}

bool device_tree_read_range(const uint8_t *entry, uint32_t address_cells, uint32_t size_cells,
                            struct memory_range *range)
{
    const uint8_t *size = entry + address_cells * DEVICE_TREE_CELL_BYTES;

    return device_tree_read_cells(entry, address_cells, &range->base) &&
           device_tree_read_cells(size, size_cells, &range->length);
}
