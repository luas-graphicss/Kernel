#include "kernel/devices/device_tree.h"

#include "tokens.h"

#define DEFAULT_ADDRESS_CELLS 2u
#define DEFAULT_SIZE_CELLS 1u
#define ROOT_DEPTH 1u
#define ROOT_CHILD_DEPTH 2u

struct open_node {
    uint32_t child_address_cells;
    uint32_t child_size_cells;
    const uint8_t *registers;
    uint32_t registers_bytes;
    bool is_memory;
    bool is_console;
    bool is_chosen;
    bool holds_reservations;
};

struct module_bounds {
    bool has_start;
    bool has_end;
    uint64_t start;
    uint64_t end;
};

struct boot_scan {
    struct boot_description *description;
    struct open_node nodes[DEVICE_TREE_MAX_DEPTH];
    uint32_t depth;
    struct module_bounds module;
    bool memory_found;
    bool console_found;
};

static bool text_equals(const char *left, const char *right)
{
    while (*left != '\0' && *left == *right) {
        left++;
        right++;
    }
    return *left == *right;
}

static bool bytes_are_text(const uint8_t *bytes, uint32_t length, const char *text)
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

static bool list_has_text(const struct device_tree_token *property, const char *text)
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
        if (bytes_are_text(property->value + start, end - start + 1u, text)) {
            return true;
        }
        start = end + 1u;
    }
    return false;
}

static bool read_cells(const uint8_t *bytes, uint32_t cells, uint64_t *value)
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

static uint32_t register_entry_bytes(const struct open_node *parent)
{
    return (parent->child_address_cells + parent->child_size_cells) * DEVICE_TREE_CELL_BYTES;
}

static enum device_tree_status read_register_entry(const struct open_node *parent,
                                                   const uint8_t *entry, struct memory_range *range)
{
    const uint8_t *size = entry + parent->child_address_cells * DEVICE_TREE_CELL_BYTES;

    if (!read_cells(entry, parent->child_address_cells, &range->base) ||
        !read_cells(size, parent->child_size_cells, &range->length)) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    return DEVICE_TREE_OK;
}

static enum device_tree_status read_first_register(const struct open_node *parent,
                                                   const struct open_node *node,
                                                   struct memory_range *range)
{
    if (node->registers == NULL || node->registers_bytes < register_entry_bytes(parent)) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    return read_register_entry(parent, node->registers, range);
}

static enum device_tree_status append_reserved(struct boot_description *description,
                                               struct memory_range range)
{
    if (description->reserved_count == DEVICE_TREE_MAX_RESERVATIONS) {
        return DEVICE_TREE_TOO_MANY_RANGES;
    }
    description->reserved[description->reserved_count] = range;
    description->reserved_count++;
    return DEVICE_TREE_OK;
}

static enum device_tree_status collect_reserved_node(struct boot_description *description,
                                                     const struct open_node *parent,
                                                     const struct open_node *node)
{
    uint32_t entry_bytes = register_entry_bytes(parent);

    if (node->registers == NULL) {
        return DEVICE_TREE_OK;
    }
    if (entry_bytes == 0 || node->registers_bytes % entry_bytes != 0) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    for (uint32_t offset = 0; offset < node->registers_bytes; offset += entry_bytes) {
        struct memory_range range;
        enum device_tree_status status =
            read_register_entry(parent, node->registers + offset, &range);
        if (status == DEVICE_TREE_OK) {
            status = append_reserved(description, range);
        }
        if (status != DEVICE_TREE_OK) {
            return status;
        }
    }
    return DEVICE_TREE_OK;
}

static enum device_tree_status collect_reservation_block(const struct device_tree *tree,
                                                         struct boot_description *description)
{
    for (uint32_t index = 0;; index++) {
        struct memory_range range;
        bool is_last;
        enum device_tree_status status = device_tree_read_reservation(tree, index, &range, &is_last);
        if (status != DEVICE_TREE_OK || is_last) {
            return status;
        }
        status = append_reserved(description, range);
        if (status != DEVICE_TREE_OK) {
            return status;
        }
    }
}

static enum device_tree_status read_cell_count(const struct device_tree_token *property,
                                               uint32_t *cells)
{
    if (property->value_bytes != DEVICE_TREE_CELL_BYTES) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    *cells = device_tree_read_be32(property->value);
    return DEVICE_TREE_OK;
}

static enum device_tree_status read_address(const struct device_tree_token *property,
                                            uint64_t *address)
{
    if (property->value_bytes % DEVICE_TREE_CELL_BYTES != 0 ||
        !read_cells(property->value, property->value_bytes / DEVICE_TREE_CELL_BYTES, address)) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    return DEVICE_TREE_OK;
}

static enum device_tree_status read_arguments(const struct device_tree_token *property,
                                              const char **arguments)
{
    if (property->value_bytes == 0 || property->value_bytes > DEVICE_TREE_MAX_ARGUMENT_BYTES + 1u ||
        property->value[property->value_bytes - 1u] != 0) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    *arguments = (const char *)property->value;
    return DEVICE_TREE_OK;
}

static enum device_tree_status scan_chosen_property(struct boot_scan *scan,
                                                    const struct device_tree_token *property)
{
    if (text_equals(property->name, "bootargs")) {
        return read_arguments(property, &scan->description->arguments);
    }
    if (text_equals(property->name, "linux,initrd-start")) {
        scan->module.has_start = true;
        return read_address(property, &scan->module.start);
    }
    if (text_equals(property->name, "linux,initrd-end")) {
        scan->module.has_end = true;
        return read_address(property, &scan->module.end);
    }
    return DEVICE_TREE_OK;
}

static enum device_tree_status scan_property(struct boot_scan *scan,
                                             const struct device_tree_token *property)
{
    if (scan->depth == 0) {
        return DEVICE_TREE_BAD_STRUCTURE;
    }
    struct open_node *node = &scan->nodes[scan->depth - 1u];

    if (text_equals(property->name, "#address-cells")) {
        return read_cell_count(property, &node->child_address_cells);
    }
    if (text_equals(property->name, "#size-cells")) {
        return read_cell_count(property, &node->child_size_cells);
    }
    if (text_equals(property->name, "reg")) {
        node->registers = property->value;
        node->registers_bytes = property->value_bytes;
        return DEVICE_TREE_OK;
    }
    if (text_equals(property->name, "device_type")) {
        node->is_memory = scan->depth == ROOT_CHILD_DEPTH &&
                          bytes_are_text(property->value, property->value_bytes, "memory");
        return DEVICE_TREE_OK;
    }
    if (text_equals(property->name, "compatible")) {
        node->is_console = list_has_text(property, "ns16550a");
        return DEVICE_TREE_OK;
    }
    if (node->is_chosen) {
        return scan_chosen_property(scan, property);
    }
    return DEVICE_TREE_OK;
}

static enum device_tree_status scan_begin_node(struct boot_scan *scan, const char *name)
{
    bool is_root_child = scan->depth == ROOT_DEPTH;

    if (scan->depth == DEVICE_TREE_MAX_DEPTH) {
        return DEVICE_TREE_TOO_DEEP;
    }
    scan->nodes[scan->depth] = (struct open_node){
        .child_address_cells = DEFAULT_ADDRESS_CELLS,
        .child_size_cells = DEFAULT_SIZE_CELLS,
        .is_chosen = is_root_child && text_equals(name, "chosen"),
        .holds_reservations = is_root_child && text_equals(name, "reserved-memory"),
    };
    scan->depth++;
    return DEVICE_TREE_OK;
}

static enum device_tree_status finish_module(struct boot_scan *scan)
{
    const struct module_bounds *module = &scan->module;

    if (!module->has_start && !module->has_end) {
        return DEVICE_TREE_OK;
    }
    if (!module->has_start || !module->has_end || module->end <= module->start) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    scan->description->has_boot_module = true;
    scan->description->boot_module = (struct memory_range){
        .base = module->start,
        .length = module->end - module->start,
    };
    return DEVICE_TREE_OK;
}

static enum device_tree_status finish_memory(struct boot_scan *scan, const struct open_node *parent,
                                             const struct open_node *node)
{
    if (scan->memory_found || node->registers_bytes > register_entry_bytes(parent)) {
        return DEVICE_TREE_TOO_MANY_RANGES;
    }
    scan->memory_found = true;
    return read_first_register(parent, node, &scan->description->memory);
}

static enum device_tree_status scan_end_node(struct boot_scan *scan)
{
    if (scan->depth == 0) {
        return DEVICE_TREE_BAD_STRUCTURE;
    }
    const struct open_node *node = &scan->nodes[scan->depth - 1u];
    scan->depth--;

    if (node->is_chosen) {
        return finish_module(scan);
    }
    if (scan->depth == 0) {
        return DEVICE_TREE_OK;
    }

    const struct open_node *parent = &scan->nodes[scan->depth - 1u];
    if (parent->holds_reservations) {
        return collect_reserved_node(scan->description, parent, node);
    }
    if (node->is_memory) {
        return finish_memory(scan, parent, node);
    }
    if (node->is_console && !scan->console_found) {
        scan->console_found = true;
        return read_first_register(parent, node, &scan->description->console);
    }
    return DEVICE_TREE_OK;
}

static enum device_tree_status finish_scan(const struct boot_scan *scan)
{
    if (!scan->memory_found) {
        return DEVICE_TREE_MISSING_MEMORY;
    }
    if (!scan->console_found) {
        return DEVICE_TREE_MISSING_CONSOLE;
    }
    return DEVICE_TREE_OK;
}

enum device_tree_status device_tree_describe_boot(const struct device_tree *tree,
                                                  struct boot_description *description)
{
    struct boot_scan scan = {.description = description};
    struct device_tree_cursor cursor = {.tree = tree};

    *description = (struct boot_description){0};
    enum device_tree_status status = collect_reservation_block(tree, description);

    while (status == DEVICE_TREE_OK) {
        struct device_tree_token token;
        status = device_tree_next_token(&cursor, &token);
        if (status != DEVICE_TREE_OK) {
            break;
        }
        switch (token.kind) {
        case DEVICE_TREE_TOKEN_BEGIN_NODE:
            status = scan_begin_node(&scan, token.name);
            break;
        case DEVICE_TREE_TOKEN_PROPERTY:
            status = scan_property(&scan, &token);
            break;
        case DEVICE_TREE_TOKEN_END_NODE:
            status = scan_end_node(&scan);
            break;
        case DEVICE_TREE_TOKEN_END:
            return finish_scan(&scan);
        default:
            break;
        }
    }
    return status;
}
