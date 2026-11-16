#ifndef TESTS_NATIVE_SUPPORT_DEVICE_TREE_BUILDER_H
#define TESTS_NATIVE_SUPPORT_DEVICE_TREE_BUILDER_H

#include <stddef.h>
#include <stdint.h>

#define BUILDER_STRUCTURE_CAPACITY 4096u
#define BUILDER_STRINGS_CAPACITY 1024u
#define BUILDER_RESERVATION_CAPACITY 32u
#define BUILDER_HEADER_BYTES 40u

struct device_tree_builder {
    uint8_t structure[BUILDER_STRUCTURE_CAPACITY];
    size_t structure_bytes;
    char strings[BUILDER_STRINGS_CAPACITY];
    size_t strings_bytes;
    uint64_t reservations[2u * BUILDER_RESERVATION_CAPACITY];
    size_t reservation_count;
};

void builder_begin_node(struct device_tree_builder *builder, const char *name);
void builder_end_node(struct device_tree_builder *builder);
void builder_token(struct device_tree_builder *builder, uint32_t token);
void builder_property(struct device_tree_builder *builder, const char *name, const void *value,
                      size_t bytes);
void builder_cells(struct device_tree_builder *builder, const char *name, const uint32_t *cells,
                   size_t count);
void builder_text(struct device_tree_builder *builder, const char *name, const char *text);
void builder_reserve(struct device_tree_builder *builder, uint64_t base, uint64_t length);
size_t builder_finish(struct device_tree_builder *builder, uint8_t *blob, size_t capacity);

void blob_write_be32(uint8_t *blob, size_t offset, uint32_t value);
uint32_t blob_read_be32(const uint8_t *blob, size_t offset);

#endif
