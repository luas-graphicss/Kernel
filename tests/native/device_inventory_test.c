#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "check.h"
#include "device_tree_builder.h"
#include "kernel/devices/device_inventory.h"
#include "kernel/devices/device_tree.h"

#define BLOB_CAPACITY 8192u
#define NAME_CAPACITY 32u
#define CELL_BYTES 4u
#define FUZZ_SEED 0x44455649u
#define FUZZ_ITERATIONS 20000u
#define CONTROLLER_BASE 0x0c000000u
#define CONTROLLER_BYTES 0x00600000u
#define CONTROLLER_SOURCES 95u
#define PROCESSOR_PHANDLE 2u
#define MACHINE_EXTERNAL_INTERRUPT 11u
#define SUPERVISOR_EXTERNAL_INTERRUPT 9u
#define MACHINE_AND_SUPERVISOR_CELLS 4u
#define MACHINE_ONLY_CELLS 2u
#define SERIAL_BASE 0x10000000u
#define SERIAL_BYTES 0x100u
#define SERIAL_INTERRUPT 10u
#define TRANSPORT_BASE 0x10001000u
#define TRANSPORT_BYTES 0x1000u
#define REFERENCE_TRANSPORTS 3u
#define RANGE_CELLS 4u

struct machine {
    uint32_t controllers;
    uint32_t sources;
    uint32_t context_cells;
    uint32_t serials;
    uint32_t serial_interrupt_bytes;
    uint32_t transports;
    uint32_t transport_register_cells;
    uint32_t transport_interrupt_bytes;
    uint32_t first_transport_interrupt;
};

static const struct machine REFERENCE = {
    .controllers = 1,
    .sources = CONTROLLER_SOURCES,
    .context_cells = MACHINE_AND_SUPERVISOR_CELLS,
    .serials = 1,
    .serial_interrupt_bytes = CELL_BYTES,
    .transports = REFERENCE_TRANSPORTS,
    .transport_register_cells = RANGE_CELLS,
    .transport_interrupt_bytes = CELL_BYTES,
    .first_transport_interrupt = 1,
};

static void add_cell_counts(struct device_tree_builder *builder, uint32_t address, uint32_t size)
{
    builder_cells(builder, "#address-cells", &address, 1);
    builder_cells(builder, "#size-cells", &size, 1);
}

static void add_interrupt(struct device_tree_builder *builder, uint32_t interrupt, uint32_t bytes)
{
    uint8_t encoded[CELL_BYTES];

    if (bytes == 0) {
        return;
    }
    blob_write_be32(encoded, 0, interrupt);
    builder_property(builder, "interrupts", encoded, bytes);
}

static void add_controller(struct device_tree_builder *builder, const struct machine *machine)
{
    const uint32_t registers[] = {0, CONTROLLER_BASE, 0, CONTROLLER_BYTES};
    const uint32_t contexts[] = {PROCESSOR_PHANDLE, MACHINE_EXTERNAL_INTERRUPT, PROCESSOR_PHANDLE,
                                 SUPERVISOR_EXTERNAL_INTERRUPT};
    const char compatible[] = "sifive,plic-1.0.0\0riscv,plic0";

    builder_begin_node(builder, "plic@c000000");
    builder_property(builder, "compatible", compatible, sizeof(compatible));
    builder_cells(builder, "reg", registers, RANGE_CELLS);
    builder_cells(builder, "riscv,ndev", &machine->sources, 1);
    if (machine->context_cells > 0) {
        builder_cells(builder, "interrupts-extended", contexts, machine->context_cells);
    }
    builder_end_node(builder);
}

static void add_serial(struct device_tree_builder *builder, const struct machine *machine,
                       uint32_t index)
{
    const uint32_t registers[] = {0, SERIAL_BASE + index * SERIAL_BYTES, 0, SERIAL_BYTES};
    char name[NAME_CAPACITY];

    snprintf(name, sizeof(name), "serial@%x", registers[1]);
    builder_begin_node(builder, name);
    builder_text(builder, "compatible", "ns16550a");
    builder_cells(builder, "reg", registers, RANGE_CELLS);
    add_interrupt(builder, SERIAL_INTERRUPT + index, machine->serial_interrupt_bytes);
    builder_end_node(builder);
}

static void add_transport(struct device_tree_builder *builder, const struct machine *machine,
                          uint32_t index)
{
    const uint32_t registers[] = {0, TRANSPORT_BASE + index * TRANSPORT_BYTES, 0, TRANSPORT_BYTES};
    char name[NAME_CAPACITY];

    snprintf(name, sizeof(name), "virtio_mmio@%x", registers[1]);
    builder_begin_node(builder, name);
    builder_text(builder, "compatible", "virtio,mmio");
    if (machine->transport_register_cells > 0) {
        builder_cells(builder, "reg", registers, machine->transport_register_cells);
    }
    add_interrupt(builder, machine->first_transport_interrupt + index,
                  machine->transport_interrupt_bytes);
    builder_end_node(builder);
}

static size_t build_tree(const struct machine *machine, uint8_t *blob)
{
    struct device_tree_builder builder = {0};

    builder_begin_node(&builder, "");
    add_cell_counts(&builder, 2, 2);
    builder_begin_node(&builder, "soc");
    add_cell_counts(&builder, 2, 2);
    for (uint32_t index = 0; index < machine->controllers; index++) {
        add_controller(&builder, machine);
    }
    for (uint32_t index = 0; index < machine->serials; index++) {
        add_serial(&builder, machine, index);
    }
    for (uint32_t index = machine->transports; index > 0; index--) {
        add_transport(&builder, machine, index - 1u);
    }
    builder_end_node(&builder);
    builder_end_node(&builder);
    return builder_finish(&builder, blob, BLOB_CAPACITY);
}

static enum device_tree_status describe_blob(const uint8_t *blob, size_t bytes,
                                             struct device_inventory *inventory)
{
    struct device_tree tree;
    enum device_tree_status status = device_tree_open(blob, bytes, &tree);

    if (status != DEVICE_TREE_OK) {
        return status;
    }
    return device_tree_describe_devices(&tree, inventory);
}

static enum device_tree_status describe(const struct machine *machine,
                                        struct device_inventory *inventory)
{
    uint8_t blob[BLOB_CAPACITY];

    return describe_blob(blob, build_tree(machine, blob), inventory);
}

static enum device_tree_status status_of(const struct machine *machine)
{
    struct device_inventory inventory;

    return describe(machine, &inventory);
}

static bool transports_are_ordered(const struct device_inventory *inventory, uint32_t count)
{
    if (inventory->transport_count != count) {
        return false;
    }
    for (uint32_t index = 0; index < count; index++) {
        const struct device_description *transport = &inventory->transports[index];

        if (transport->registers.base != TRANSPORT_BASE + index * TRANSPORT_BYTES ||
            transport->registers.length != TRANSPORT_BYTES || transport->interrupt != index + 1u) {
            return false;
        }
    }
    return true;
}

static bool source_is_valid(const struct device_inventory *inventory, uint32_t interrupt)
{
    return interrupt != 0 && interrupt <= inventory->controller.sources;
}

static bool inventory_is_consistent(const struct device_inventory *inventory)
{
    if (inventory->transport_count > DEVICE_TRANSPORTS) {
        return false;
    }
    for (uint32_t index = 1; index < inventory->transport_count; index++) {
        if (inventory->transports[index - 1u].registers.base >
            inventory->transports[index].registers.base) {
            return false;
        }
    }
    if (!inventory->controller.present) {
        return true;
    }
    if (inventory->controller.sources == 0 ||
        inventory->controller.sources > INTERRUPT_SOURCE_LIMIT) {
        return false;
    }
    if (inventory->has_serial && !source_is_valid(inventory, inventory->serial.interrupt)) {
        return false;
    }
    for (uint32_t index = 0; index < inventory->transport_count; index++) {
        if (!source_is_valid(inventory, inventory->transports[index].interrupt)) {
            return false;
        }
    }
    return true;
}

static void test_reference_machine_is_described(void)
{
    struct device_inventory inventory;

    CHECK(describe(&REFERENCE, &inventory) == DEVICE_TREE_OK);
    CHECK(inventory.controller.present);
    CHECK(inventory.controller.registers.base == CONTROLLER_BASE);
    CHECK(inventory.controller.registers.length == CONTROLLER_BYTES);
    CHECK(inventory.controller.sources == CONTROLLER_SOURCES);
    CHECK(inventory.controller.supervisor_context == 1);
    CHECK(inventory.has_serial && inventory.serial.interrupt == SERIAL_INTERRUPT);
    CHECK(inventory.serial.registers.base == SERIAL_BASE);
    CHECK(inventory.serial.registers.length == SERIAL_BYTES);
    CHECK(transports_are_ordered(&inventory, REFERENCE_TRANSPORTS));
}

static void test_a_machine_without_a_supervisor_controller_is_still_described(void)
{
    struct machine machine = REFERENCE;
    struct device_inventory inventory;

    machine.controllers = 0;
    CHECK(describe(&machine, &inventory) == DEVICE_TREE_OK);
    CHECK(!inventory.controller.present && inventory.has_serial);
    CHECK(transports_are_ordered(&inventory, REFERENCE_TRANSPORTS));

    machine = REFERENCE;
    machine.context_cells = MACHINE_ONLY_CELLS;
    CHECK(describe(&machine, &inventory) == DEVICE_TREE_OK);
    CHECK(!inventory.controller.present);
}

static void test_malformed_controllers_are_rejected(void)
{
    struct machine machine = REFERENCE;

    machine.controllers = 2;
    CHECK(status_of(&machine) == DEVICE_TREE_TOO_MANY_RANGES);

    machine = REFERENCE;
    machine.sources = 0;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
    machine.sources = INTERRUPT_SOURCE_LIMIT + 1u;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
    machine.sources = INTERRUPT_SOURCE_LIMIT;
    CHECK(status_of(&machine) == DEVICE_TREE_OK);

    machine = REFERENCE;
    machine.context_cells = 0;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
    machine.context_cells = MACHINE_ONLY_CELLS + 1u;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
}

static void test_serial_port_needs_an_interrupt_and_only_the_first_counts(void)
{
    struct machine machine = REFERENCE;
    struct device_inventory inventory;

    machine.serial_interrupt_bytes = 0;
    CHECK(describe(&machine, &inventory) == DEVICE_TREE_OK && !inventory.has_serial);

    machine = REFERENCE;
    machine.serials = 0;
    CHECK(describe(&machine, &inventory) == DEVICE_TREE_OK && !inventory.has_serial);

    machine = REFERENCE;
    machine.serials = 2;
    CHECK(describe(&machine, &inventory) == DEVICE_TREE_OK && inventory.has_serial);
    CHECK(inventory.serial.registers.base == SERIAL_BASE);
    CHECK(inventory.serial.interrupt == SERIAL_INTERRUPT);

    machine = REFERENCE;
    machine.serial_interrupt_bytes = CELL_BYTES / 2u;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
}

static void test_malformed_transports_are_rejected(void)
{
    struct machine machine = REFERENCE;

    machine.transport_interrupt_bytes = 0;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
    machine.transport_interrupt_bytes = CELL_BYTES / 2u;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);

    machine = REFERENCE;
    machine.transport_register_cells = 0;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
    machine.transport_register_cells = RANGE_CELLS - 1u;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
}

static void test_interrupts_must_be_sources_of_the_controller(void)
{
    struct machine machine = REFERENCE;

    machine.first_transport_interrupt = 0;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
    machine.first_transport_interrupt = CONTROLLER_SOURCES - REFERENCE_TRANSPORTS + 2u;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
    machine.first_transport_interrupt = CONTROLLER_SOURCES - REFERENCE_TRANSPORTS + 1u;
    CHECK(status_of(&machine) == DEVICE_TREE_OK);

    machine = REFERENCE;
    machine.sources = SERIAL_INTERRUPT - 1u;
    CHECK(status_of(&machine) == DEVICE_TREE_BAD_PROPERTY);
}

static void test_transport_count_is_bounded(void)
{
    struct machine machine = REFERENCE;
    struct device_inventory inventory;

    machine.transports = DEVICE_TRANSPORTS;
    CHECK(describe(&machine, &inventory) == DEVICE_TREE_OK);
    CHECK(transports_are_ordered(&inventory, DEVICE_TRANSPORTS));
    machine.transports = DEVICE_TRANSPORTS + 1u;
    CHECK(status_of(&machine) == DEVICE_TREE_TOO_MANY_RANGES);
}

static uint32_t next_random(uint32_t *state)
{
    *state ^= *state << 13;
    *state ^= *state >> 17;
    *state ^= *state << 5;
    return *state;
}

static void test_mutated_trees_never_describe_an_inconsistent_machine(void)
{
    uint8_t reference[BLOB_CAPACITY];
    size_t bytes = build_tree(&REFERENCE, reference);
    uint32_t state = FUZZ_SEED;
    uint32_t accepted = 0;

    for (uint32_t iteration = 0; iteration < FUZZ_ITERATIONS; iteration++) {
        uint8_t *mutated = malloc(bytes);
        if (mutated == NULL) {
            abort();
        }
        memcpy(mutated, reference, bytes);
        uint32_t mutations = 1u + next_random(&state) % 3u;
        for (uint32_t mutation = 0; mutation < mutations; mutation++) {
            mutated[next_random(&state) % bytes] = (uint8_t)next_random(&state);
        }

        struct device_inventory inventory;
        if (describe_blob(mutated, bytes, &inventory) == DEVICE_TREE_OK) {
            accepted++;
            CHECK(inventory_is_consistent(&inventory));
        }
        free(mutated);
    }
    CHECK(accepted > 0);
    CHECK(accepted < FUZZ_ITERATIONS);
}

int main(void)
{
    test_reference_machine_is_described();
    test_a_machine_without_a_supervisor_controller_is_still_described();
    test_malformed_controllers_are_rejected();
    test_serial_port_needs_an_interrupt_and_only_the_first_counts();
    test_malformed_transports_are_rejected();
    test_interrupts_must_be_sources_of_the_controller();
    test_transport_count_is_bounded();
    test_mutated_trees_never_describe_an_inconsistent_machine();
    return check_finish("device-inventory");
}
