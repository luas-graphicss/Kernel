#ifndef KERNEL_SUPERVISOR_DEVICE_TREE_PROPERTIES_H
#define KERNEL_SUPERVISOR_DEVICE_TREE_PROPERTIES_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/memory/range.h"
#include "tokens.h"

bool device_tree_text_equals(const char *left, const char *right);
bool device_tree_value_is_text(const uint8_t *bytes, uint32_t length, const char *text);
bool device_tree_list_has_text(const struct device_tree_token *property, const char *text);
bool device_tree_read_cells(const uint8_t *bytes, uint32_t cells, uint64_t *value);
uint32_t device_tree_range_bytes(uint32_t address_cells, uint32_t size_cells);
bool device_tree_read_range(const uint8_t *entry, uint32_t address_cells, uint32_t size_cells,
                            struct memory_range *range);

#endif
