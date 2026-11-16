#include "kernel/devices/device_inventory.h"

#include <stddef.h>

#include "properties.h"
#include "tokens.h"

#define DEFAULT_ADDRESS_CELLS 2u
#define DEFAULT_SIZE_CELLS 1u
#define CONTEXT_ENTRY_BYTES (2u * DEVICE_TREE_CELL_BYTES)
#define SUPERVISOR_EXTERNAL_INTERRUPT 9u

struct scanned_node {
    uint32_t child_address_cells;
    uint32_t child_size_cells;
    const uint8_t *registers;
    uint32_t registers_bytes;
    const uint8_t *contexts;
    uint32_t contexts_bytes;
    uint32_t interrupt;
    uint32_t sources;
    bool has_interrupt;
    bool is_controller;
    bool is_serial;
    bool is_transport;
};

struct device_scan {
    struct device_inventory *inventory;
    struct scanned_node nodes[DEVICE_TREE_MAX_DEPTH];
    uint32_t depth;
    bool serial_seen;
};

static enum device_tree_status read_cell(const struct device_tree_token *property, uint32_t *cell)
{
    if (property->value_bytes != DEVICE_TREE_CELL_BYTES) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    *cell = device_tree_read_be32(property->value);
    return DEVICE_TREE_OK;
}

static enum device_tree_status read_interrupt(const struct device_tree_token *property,
                                              struct scanned_node *node)
{
    if (property->value_bytes < DEVICE_TREE_CELL_BYTES ||
        property->value_bytes % DEVICE_TREE_CELL_BYTES != 0) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    node->interrupt = device_tree_read_be32(property->value);
    node->has_interrupt = true;
    return DEVICE_TREE_OK;
}

static void classify(const struct device_tree_token *property, struct scanned_node *node)
{
    node->is_controller = device_tree_list_has_text(property, "sifive,plic-1.0.0") ||
                          device_tree_list_has_text(property, "riscv,plic0");
    node->is_serial = device_tree_list_has_text(property, "ns16550a");
    node->is_transport = device_tree_list_has_text(property, "virtio,mmio");
}

static enum device_tree_status scan_property(struct device_scan *scan,
                                             const struct device_tree_token *property)
{
    struct scanned_node *node;

    if (scan->depth == 0) {
        return DEVICE_TREE_BAD_STRUCTURE;
    }
    node = &scan->nodes[scan->depth - 1u];
    if (device_tree_text_equals(property->name, "#address-cells")) {
        return read_cell(property, &node->child_address_cells);
    }
    if (device_tree_text_equals(property->name, "#size-cells")) {
        return read_cell(property, &node->child_size_cells);
    }
    if (device_tree_text_equals(property->name, "riscv,ndev")) {
        return read_cell(property, &node->sources);
    }
    if (device_tree_text_equals(property->name, "interrupts")) {
        return read_interrupt(property, node);
    }
    if (device_tree_text_equals(property->name, "reg")) {
        node->registers = property->value;
        node->registers_bytes = property->value_bytes;
    } else if (device_tree_text_equals(property->name, "interrupts-extended")) {
        node->contexts = property->value;
        node->contexts_bytes = property->value_bytes;
    } else if (device_tree_text_equals(property->name, "compatible")) {
        classify(property, node);
    }
    return DEVICE_TREE_OK;
}

static enum device_tree_status scan_begin_node(struct device_scan *scan)
{
    if (scan->depth == DEVICE_TREE_MAX_DEPTH) {
        return DEVICE_TREE_TOO_DEEP;
    }
    scan->nodes[scan->depth] = (struct scanned_node){
        .child_address_cells = DEFAULT_ADDRESS_CELLS,
        .child_size_cells = DEFAULT_SIZE_CELLS,
    };
    scan->depth++;
    return DEVICE_TREE_OK;
}

static enum device_tree_status read_registers(const struct scanned_node *parent,
                                              const struct scanned_node *node,
                                              struct memory_range *range)
{
    uint32_t entry_bytes =
        device_tree_range_bytes(parent->child_address_cells, parent->child_size_cells);

    if (node->registers == NULL || node->registers_bytes < entry_bytes ||
        !device_tree_read_range(node->registers, parent->child_address_cells,
                                parent->child_size_cells, range)) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    return DEVICE_TREE_OK;
}

static bool find_supervisor_context(const struct scanned_node *node, uint32_t *context)
{
    for (uint32_t offset = 0; offset < node->contexts_bytes; offset += CONTEXT_ENTRY_BYTES) {
        const uint8_t *cause = node->contexts + offset + DEVICE_TREE_CELL_BYTES;

        if (device_tree_read_be32(cause) == SUPERVISOR_EXTERNAL_INTERRUPT) {
            *context = offset / CONTEXT_ENTRY_BYTES;
            return true;
        }
    }
    return false;
}

static enum device_tree_status finish_controller(struct device_scan *scan,
                                                 const struct scanned_node *parent,
                                                 const struct scanned_node *node)
{
    struct interrupt_controller_description *controller = &scan->inventory->controller;

    if (controller->present) {
        return DEVICE_TREE_TOO_MANY_RANGES;
    }
    if (node->contexts == NULL || node->contexts_bytes % CONTEXT_ENTRY_BYTES != 0 ||
        node->sources == 0 || node->sources > INTERRUPT_SOURCE_LIMIT) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    if (!find_supervisor_context(node, &controller->supervisor_context)) {
        return DEVICE_TREE_OK;
    }
    controller->present = true;
    controller->sources = node->sources;
    return read_registers(parent, node, &controller->registers);
}

static enum device_tree_status finish_serial(struct device_scan *scan,
                                             const struct scanned_node *parent,
                                             const struct scanned_node *node)
{
    struct device_inventory *inventory = scan->inventory;

    if (scan->serial_seen) {
        return DEVICE_TREE_OK;
    }
    scan->serial_seen = true;
    if (!node->has_interrupt) {
        return DEVICE_TREE_OK;
    }
    inventory->has_serial = true;
    inventory->serial.interrupt = node->interrupt;
    return read_registers(parent, node, &inventory->serial.registers);
}

static enum device_tree_status finish_transport(struct device_scan *scan,
                                                const struct scanned_node *parent,
                                                const struct scanned_node *node)
{
    struct device_inventory *inventory = scan->inventory;
    struct device_description found = {.interrupt = node->interrupt};
    uint32_t position = inventory->transport_count;
    enum device_tree_status status;

    if (inventory->transport_count == DEVICE_TRANSPORTS) {
        return DEVICE_TREE_TOO_MANY_RANGES;
    }
    if (!node->has_interrupt) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    status = read_registers(parent, node, &found.registers);
    if (status != DEVICE_TREE_OK) {
        return status;
    }
    while (position > 0 && inventory->transports[position - 1u].registers.base > found.registers.base) {
        inventory->transports[position] = inventory->transports[position - 1u];
        position--;
    }
    inventory->transports[position] = found;
    inventory->transport_count++;
    return DEVICE_TREE_OK;
}

static enum device_tree_status scan_end_node(struct device_scan *scan)
{
    const struct scanned_node *node;
    const struct scanned_node *parent;

    if (scan->depth == 0) {
        return DEVICE_TREE_BAD_STRUCTURE;
    }
    node = &scan->nodes[scan->depth - 1u];
    scan->depth--;
    if (scan->depth == 0) {
        return DEVICE_TREE_OK;
    }
    parent = &scan->nodes[scan->depth - 1u];
    if (node->is_controller) {
        return finish_controller(scan, parent, node);
    }
    if (node->is_serial) {
        return finish_serial(scan, parent, node);
    }
    if (node->is_transport) {
        return finish_transport(scan, parent, node);
    }
    return DEVICE_TREE_OK;
}

static bool source_is_valid(uint32_t interrupt, uint32_t sources)
{
    return interrupt != 0 && interrupt <= sources;
}

static enum device_tree_status finish_scan(const struct device_inventory *inventory)
{
    uint32_t sources = inventory->controller.sources;

    if (!inventory->controller.present) {
        return DEVICE_TREE_OK;
    }
    if (inventory->has_serial && !source_is_valid(inventory->serial.interrupt, sources)) {
        return DEVICE_TREE_BAD_PROPERTY;
    }
    for (uint32_t index = 0; index < inventory->transport_count; index++) {
        if (!source_is_valid(inventory->transports[index].interrupt, sources)) {
            return DEVICE_TREE_BAD_PROPERTY;
        }
    }
    return DEVICE_TREE_OK;
}

enum device_tree_status device_tree_describe_devices(const struct device_tree *tree,
                                                     struct device_inventory *inventory)
{
    struct device_scan scan = {.inventory = inventory};
    struct device_tree_cursor cursor = {.tree = tree};

    *inventory = (struct device_inventory){0};
    for (;;) {
        struct device_tree_token token;
        enum device_tree_status status = device_tree_next_token(&cursor, &token);

        if (status != DEVICE_TREE_OK) {
            return status;
        }
        switch (token.kind) {
        case DEVICE_TREE_TOKEN_BEGIN_NODE:
            status = scan_begin_node(&scan);
            break;
        case DEVICE_TREE_TOKEN_PROPERTY:
            status = scan_property(&scan, &token);
            break;
        case DEVICE_TREE_TOKEN_END_NODE:
            status = scan_end_node(&scan);
            break;
        case DEVICE_TREE_TOKEN_END:
            return finish_scan(inventory);
        default:
            break;
        }
        if (status != DEVICE_TREE_OK) {
            return status;
        }
    }
}
