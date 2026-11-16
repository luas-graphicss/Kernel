#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "check.h"
#include "device_tree_builder.h"
#include "kernel/devices/device_tree.h"

#define BLOB_CAPACITY 8192u
#define FUZZ_SEED 0x4b524e4cu
#define FUZZ_ITERATIONS 20000u
#define TOKEN_NOP 4u
#define TOKEN_PROPERTY 3u
#define TOKEN_END 9u
#define TOKEN_UNKNOWN 7u

#define HEADER_TOTAL_BYTES 4u
#define HEADER_STRUCTURE_OFFSET 8u
#define HEADER_RESERVATIONS_OFFSET 16u
#define HEADER_VERSION 20u
#define HEADER_COMPATIBLE_VERSION 24u
#define HEADER_STRINGS_BYTES 32u
#define HEADER_STRUCTURE_BYTES 36u

enum variant {
    VARIANT_REFERENCE,
    VARIANT_WITHOUT_MEMORY,
    VARIANT_TWO_MEMORY_NODES,
    VARIANT_TWO_MEMORY_RANGES,
    VARIANT_WITHOUT_CONSOLE,
    VARIANT_MODULE_WITHOUT_END,
    VARIANT_UNTERMINATED_ARGUMENTS,
    VARIANT_TOO_MANY_RESERVED_NODES,
    VARIANT_WIDE_ADDRESS_CELLS,
    VARIANT_WITHOUT_TIMEBASE,
    VARIANT_WIDE_TIMEBASE,
};

static void add_cell_counts(struct device_tree_builder *builder, uint32_t address, uint32_t size)
{
    builder_cells(builder, "#address-cells", &address, 1);
    builder_cells(builder, "#size-cells", &size, 1);
}

static void add_memory_node(struct device_tree_builder *builder, bool two_ranges)
{
    const uint32_t ranges[] = {0, 0x80000000u, 0, 0x10000000u, 0, 0x90000000u, 0, 0x10000000u};

    builder_begin_node(builder, "memory@80000000");
    builder_text(builder, "device_type", "memory");
    builder_cells(builder, "reg", ranges, two_ranges ? 8u : 4u);
    builder_end_node(builder);
}

static void add_reserved_nodes(struct device_tree_builder *builder, uint32_t count)
{
    builder_begin_node(builder, "reserved-memory");
    add_cell_counts(builder, 2, 2);
    for (uint32_t index = 0; index < count; index++) {
        const uint32_t range[] = {0, 0x80000000u + index * 0x40000u, 0, 0x40000u};

        builder_begin_node(builder, "firmware");
        builder_cells(builder, "reg", range, 4);
        builder_end_node(builder);
    }
    builder_end_node(builder);
}

static void add_processors(struct device_tree_builder *builder, enum variant variant)
{
    const uint32_t identifier[] = {0};
    const uint32_t timebase[] = {0, 10000000u, 0};

    builder_begin_node(builder, "cpus");
    add_cell_counts(builder, 1, 0);
    if (variant == VARIANT_WIDE_TIMEBASE) {
        builder_cells(builder, "timebase-frequency", timebase, 3);
    } else if (variant != VARIANT_WITHOUT_TIMEBASE) {
        builder_cells(builder, "timebase-frequency", timebase + 1, 1);
    }
    builder_begin_node(builder, "cpu@0");
    builder_cells(builder, "reg", identifier, 1);
    builder_end_node(builder);
    builder_end_node(builder);
}

static void add_chosen(struct device_tree_builder *builder, enum variant variant)
{
    const uint32_t module_start[] = {0, 0x88200000u};
    const uint32_t module_end[] = {0, 0x88201000u};

    builder_begin_node(builder, "chosen");
    if (variant == VARIANT_UNTERMINATED_ARGUMENTS) {
        builder_property(builder, "bootargs", "open", 4);
    } else {
        builder_text(builder, "bootargs", "selftest=trap");
    }
    builder_cells(builder, "linux,initrd-start", module_start, 2);
    if (variant != VARIANT_MODULE_WITHOUT_END) {
        builder_cells(builder, "linux,initrd-end", module_end, 2);
    }
    builder_end_node(builder);
}

static void add_devices(struct device_tree_builder *builder, bool with_console)
{
    const uint32_t registers[] = {0, 0x10000000u, 0, 0x100u};
    const char compatible[] = "vendor,serial\0ns16550a";

    builder_begin_node(builder, "soc");
    add_cell_counts(builder, 2, 2);
    builder_begin_node(builder, "serial@10000000");
    if (with_console) {
        builder_property(builder, "compatible", compatible, sizeof(compatible));
    } else {
        builder_text(builder, "compatible", "ns8250");
    }
    builder_cells(builder, "reg", registers, 4);
    builder_end_node(builder);
    builder_end_node(builder);
}

static size_t build_tree(enum variant variant, uint8_t *blob)
{
    struct device_tree_builder builder = {0};
    uint32_t reserved_nodes =
        variant == VARIANT_TOO_MANY_RESERVED_NODES ? DEVICE_TREE_MAX_RESERVATIONS : 1u;

    builder_reserve(&builder, 0x8f000000ull, 0x1000);
    builder_begin_node(&builder, "");
    add_cell_counts(&builder, variant == VARIANT_WIDE_ADDRESS_CELLS ? 3u : 2u, 2);
    add_reserved_nodes(&builder, reserved_nodes);
    if (variant != VARIANT_WITHOUT_MEMORY) {
        add_memory_node(&builder, variant == VARIANT_TWO_MEMORY_RANGES);
    }
    if (variant == VARIANT_TWO_MEMORY_NODES) {
        add_memory_node(&builder, false);
    }
    add_processors(&builder, variant);
    add_chosen(&builder, variant);
    add_devices(&builder, variant != VARIANT_WITHOUT_CONSOLE);
    builder_end_node(&builder);
    return builder_finish(&builder, blob, BLOB_CAPACITY);
}

static enum device_tree_status describe(const uint8_t *blob, size_t bytes,
                                        struct boot_description *description)
{
    struct device_tree tree;
    enum device_tree_status status = device_tree_open(blob, bytes, &tree);

    if (status != DEVICE_TREE_OK) {
        return status;
    }
    return device_tree_describe_boot(&tree, description);
}

static enum device_tree_status open_status(const uint8_t *blob, size_t bytes)
{
    struct device_tree tree;

    return device_tree_open(blob, bytes, &tree);
}

static void test_reference_tree_is_described(void)
{
    uint8_t blob[BLOB_CAPACITY];
    struct boot_description description;
    size_t bytes = build_tree(VARIANT_REFERENCE, blob);

    CHECK(describe(blob, bytes, &description) == DEVICE_TREE_OK);
    CHECK(description.memory.base == 0x80000000ull);
    CHECK(description.memory.length == 0x10000000ull);
    CHECK(description.console.base == 0x10000000ull);
    CHECK(description.console.length == 0x100ull);
    CHECK(description.reserved_count == 2);
    CHECK(description.reserved[0].base == 0x8f000000ull);
    CHECK(description.reserved[1].base == 0x80000000ull);
    CHECK(description.reserved[1].length == 0x40000ull);
    CHECK(description.has_boot_module);
    CHECK(description.boot_module.base == 0x88200000ull);
    CHECK(description.boot_module.length == 0x1000ull);
    CHECK(description.arguments != NULL && strcmp(description.arguments, "selftest=trap") == 0);
    CHECK(description.has_timebase && description.timebase_frequency == 10000000ull);
}

static void test_timebase_is_optional_but_must_be_well_formed(void)
{
    uint8_t blob[BLOB_CAPACITY];
    struct boot_description description;
    size_t bytes = build_tree(VARIANT_WITHOUT_TIMEBASE, blob);

    CHECK(describe(blob, bytes, &description) == DEVICE_TREE_OK);
    CHECK(!description.has_timebase);
    bytes = build_tree(VARIANT_WIDE_TIMEBASE, blob);
    CHECK(describe(blob, bytes, &description) == DEVICE_TREE_BAD_PROPERTY);
}

static void test_incomplete_or_ambiguous_trees_are_rejected(void)
{
    static const struct {
        enum variant variant;
        enum device_tree_status expected;
    } cases[] = {
        {VARIANT_WITHOUT_MEMORY, DEVICE_TREE_MISSING_MEMORY},
        {VARIANT_TWO_MEMORY_NODES, DEVICE_TREE_TOO_MANY_RANGES},
        {VARIANT_TWO_MEMORY_RANGES, DEVICE_TREE_TOO_MANY_RANGES},
        {VARIANT_WITHOUT_CONSOLE, DEVICE_TREE_MISSING_CONSOLE},
        {VARIANT_MODULE_WITHOUT_END, DEVICE_TREE_BAD_PROPERTY},
        {VARIANT_UNTERMINATED_ARGUMENTS, DEVICE_TREE_BAD_PROPERTY},
        {VARIANT_TOO_MANY_RESERVED_NODES, DEVICE_TREE_TOO_MANY_RANGES},
        {VARIANT_WIDE_ADDRESS_CELLS, DEVICE_TREE_BAD_PROPERTY},
    };

    for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); index++) {
        uint8_t blob[BLOB_CAPACITY];
        struct boot_description description;
        size_t bytes = build_tree(cases[index].variant, blob);

        CHECK(describe(blob, bytes, &description) == cases[index].expected);
    }
}

static void test_header_fields_are_validated(void)
{
    uint8_t reference[BLOB_CAPACITY];
    size_t bytes = build_tree(VARIANT_REFERENCE, reference);
    uint32_t structure_offset = blob_read_be32(reference, HEADER_STRUCTURE_OFFSET);
    uint32_t structure_bytes = blob_read_be32(reference, HEADER_STRUCTURE_BYTES);
    uint32_t strings_bytes = blob_read_be32(reference, HEADER_STRINGS_BYTES);
    uint32_t reservations_offset = blob_read_be32(reference, HEADER_RESERVATIONS_OFFSET);
    const struct {
        size_t offset;
        uint32_t value;
        enum device_tree_status expected;
    } cases[] = {
        {0, 0, DEVICE_TREE_BAD_MAGIC},
        {HEADER_VERSION, 16, DEVICE_TREE_BAD_VERSION},
        {HEADER_COMPATIBLE_VERSION, 17, DEVICE_TREE_BAD_VERSION},
        {HEADER_TOTAL_BYTES, 39, DEVICE_TREE_BAD_LAYOUT},
        {HEADER_TOTAL_BYTES, (uint32_t)bytes + 4u, DEVICE_TREE_TOO_LARGE},
        {HEADER_RESERVATIONS_OFFSET, 32, DEVICE_TREE_BAD_LAYOUT},
        {HEADER_RESERVATIONS_OFFSET, 44, DEVICE_TREE_BAD_LAYOUT},
        {HEADER_STRUCTURE_OFFSET, structure_offset + 2u, DEVICE_TREE_BAD_LAYOUT},
        {HEADER_STRUCTURE_OFFSET, reservations_offset, DEVICE_TREE_BAD_LAYOUT},
        {HEADER_STRUCTURE_BYTES, 0, DEVICE_TREE_BAD_LAYOUT},
        {HEADER_STRUCTURE_BYTES, structure_bytes + 4u, DEVICE_TREE_BAD_LAYOUT},
        {HEADER_STRINGS_BYTES, strings_bytes + 1u, DEVICE_TREE_BAD_LAYOUT},
    };

    CHECK(open_status(NULL, bytes) == DEVICE_TREE_NULL);
    CHECK(open_status(reference, 39) == DEVICE_TREE_BAD_LAYOUT);
    for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); index++) {
        uint8_t blob[BLOB_CAPACITY];

        memcpy(blob, reference, bytes);
        blob_write_be32(blob, cases[index].offset, cases[index].value);
        CHECK(open_status(blob, bytes) == cases[index].expected);
    }
}

static enum device_tree_status finish_and_open(struct device_tree_builder *builder)
{
    uint8_t blob[BLOB_CAPACITY];
    size_t bytes = builder_finish(builder, blob, BLOB_CAPACITY);

    return open_status(blob, bytes);
}

static void test_structure_is_validated(void)
{
    struct device_tree_builder unknown_token = {0};
    builder_begin_node(&unknown_token, "");
    builder_token(&unknown_token, TOKEN_UNKNOWN);
    builder_end_node(&unknown_token);
    CHECK(finish_and_open(&unknown_token) == DEVICE_TREE_BAD_STRUCTURE);

    struct device_tree_builder property_after_child = {0};
    builder_begin_node(&property_after_child, "");
    builder_begin_node(&property_after_child, "child");
    builder_end_node(&property_after_child);
    builder_text(&property_after_child, "model", "late");
    builder_end_node(&property_after_child);
    CHECK(finish_and_open(&property_after_child) == DEVICE_TREE_BAD_STRUCTURE);

    struct device_tree_builder named_root = {0};
    builder_begin_node(&named_root, "root");
    builder_end_node(&named_root);
    CHECK(finish_and_open(&named_root) == DEVICE_TREE_BAD_STRUCTURE);

    struct device_tree_builder second_root = {0};
    builder_begin_node(&second_root, "");
    builder_end_node(&second_root);
    builder_begin_node(&second_root, "");
    builder_end_node(&second_root);
    CHECK(finish_and_open(&second_root) == DEVICE_TREE_BAD_STRUCTURE);

    struct device_tree_builder open_root = {0};
    builder_begin_node(&open_root, "");
    CHECK(finish_and_open(&open_root) == DEVICE_TREE_BAD_STRUCTURE);

    struct device_tree_builder stray_end = {0};
    builder_end_node(&stray_end);
    CHECK(finish_and_open(&stray_end) == DEVICE_TREE_BAD_STRUCTURE);

    struct device_tree_builder data_after_end = {0};
    builder_begin_node(&data_after_end, "");
    builder_end_node(&data_after_end);
    builder_token(&data_after_end, TOKEN_END);
    CHECK(finish_and_open(&data_after_end) == DEVICE_TREE_BAD_STRUCTURE);
}

static void test_depth_and_names_are_bounded(void)
{
    struct device_tree_builder deepest = {0};
    for (uint32_t depth = 0; depth < DEVICE_TREE_MAX_DEPTH; depth++) {
        builder_begin_node(&deepest, depth == 0 ? "" : "level");
    }
    for (uint32_t depth = 0; depth < DEVICE_TREE_MAX_DEPTH; depth++) {
        builder_end_node(&deepest);
    }
    CHECK(finish_and_open(&deepest) == DEVICE_TREE_OK);

    struct device_tree_builder too_deep = {0};
    for (uint32_t depth = 0; depth <= DEVICE_TREE_MAX_DEPTH; depth++) {
        builder_begin_node(&too_deep, depth == 0 ? "" : "level");
    }
    for (uint32_t depth = 0; depth <= DEVICE_TREE_MAX_DEPTH; depth++) {
        builder_end_node(&too_deep);
    }
    CHECK(finish_and_open(&too_deep) == DEVICE_TREE_TOO_DEEP);

    char long_name[DEVICE_TREE_MAX_NAME_BYTES + 2u];
    memset(long_name, 'n', sizeof(long_name) - 1u);
    long_name[sizeof(long_name) - 1u] = '\0';
    struct device_tree_builder long_node_name = {0};
    builder_begin_node(&long_node_name, "");
    builder_begin_node(&long_node_name, long_name);
    builder_end_node(&long_node_name);
    builder_end_node(&long_node_name);
    CHECK(finish_and_open(&long_node_name) == DEVICE_TREE_BAD_NAME);
}

static void test_properties_are_bounded(void)
{
    struct device_tree_builder name_outside_strings = {0};
    builder_begin_node(&name_outside_strings, "");
    builder_token(&name_outside_strings, TOKEN_PROPERTY);
    builder_token(&name_outside_strings, 0);
    builder_token(&name_outside_strings, 0xffffu);
    builder_end_node(&name_outside_strings);
    CHECK(finish_and_open(&name_outside_strings) == DEVICE_TREE_BAD_NAME);

    struct device_tree_builder value_outside_block = {0};
    builder_begin_node(&value_outside_block, "");
    builder_text(&value_outside_block, "model", "reference");
    builder_token(&value_outside_block, TOKEN_PROPERTY);
    builder_token(&value_outside_block, 0x10000u);
    builder_token(&value_outside_block, 0);
    builder_end_node(&value_outside_block);
    CHECK(finish_and_open(&value_outside_block) == DEVICE_TREE_BAD_PROPERTY);
}

static void test_reservation_block_is_bounded(void)
{
    struct device_tree_builder too_many = {0};
    for (uint64_t index = 0; index <= DEVICE_TREE_MAX_RESERVATIONS; index++) {
        builder_reserve(&too_many, 0x80000000ull + index * 0x1000u, 0x1000);
    }
    builder_begin_node(&too_many, "");
    builder_end_node(&too_many);
    CHECK(finish_and_open(&too_many) == DEVICE_TREE_TOO_MANY_RANGES);

    uint8_t blob[BLOB_CAPACITY];
    size_t bytes = build_tree(VARIANT_REFERENCE, blob);
    uint32_t terminator = blob_read_be32(blob, HEADER_RESERVATIONS_OFFSET) + 16u;
    blob_write_be32(blob, terminator + 12u, 0x1000);
    CHECK(open_status(blob, bytes) == DEVICE_TREE_BAD_LAYOUT);
}

static void test_missing_end_token_is_rejected(void)
{
    uint8_t blob[BLOB_CAPACITY];
    size_t bytes = build_tree(VARIANT_REFERENCE, blob);
    uint32_t structure_end =
        blob_read_be32(blob, HEADER_STRUCTURE_OFFSET) + blob_read_be32(blob, HEADER_STRUCTURE_BYTES);

    CHECK(blob_read_be32(blob, structure_end - 4u) == TOKEN_END);
    blob_write_be32(blob, structure_end - 4u, TOKEN_NOP);
    CHECK(open_status(blob, bytes) == DEVICE_TREE_BAD_STRUCTURE);
}

static void test_every_truncation_is_rejected(void)
{
    uint8_t reference[BLOB_CAPACITY];
    size_t bytes = build_tree(VARIANT_REFERENCE, reference);

    for (size_t length = 0; length < bytes; length++) {
        uint8_t *truncated = malloc(length == 0 ? 1u : length);
        if (truncated == NULL) {
            abort();
        }
        memcpy(truncated, reference, length);
        CHECK(open_status(truncated, length) != DEVICE_TREE_OK);
        free(truncated);
    }
}

static uint32_t next_random(uint32_t *state)
{
    *state ^= *state << 13;
    *state ^= *state >> 17;
    *state ^= *state << 5;
    return *state;
}

static void test_mutated_trees_never_escape_their_buffer(void)
{
    uint8_t reference[BLOB_CAPACITY];
    size_t bytes = build_tree(VARIANT_REFERENCE, reference);
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

        struct boot_description description;
        if (describe(mutated, bytes, &description) == DEVICE_TREE_OK) {
            accepted++;
            CHECK(description.reserved_count <= DEVICE_TREE_MAX_RESERVATIONS);
            CHECK(description.arguments == NULL ||
                  strlen(description.arguments) <= DEVICE_TREE_MAX_ARGUMENT_BYTES);
        }
        free(mutated);
    }
    CHECK(accepted > 0);
    CHECK(accepted < FUZZ_ITERATIONS);
}

int main(void)
{
    test_reference_tree_is_described();
    test_timebase_is_optional_but_must_be_well_formed();
    test_incomplete_or_ambiguous_trees_are_rejected();
    test_header_fields_are_validated();
    test_structure_is_validated();
    test_depth_and_names_are_bounded();
    test_properties_are_bounded();
    test_reservation_block_is_bounded();
    test_missing_end_token_is_rejected();
    test_every_truncation_is_rejected();
    test_mutated_trees_never_escape_their_buffer();
    return check_finish("device-tree");
}
