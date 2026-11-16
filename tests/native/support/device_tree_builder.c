#include "device_tree_builder.h"

#include <stdlib.h>
#include <string.h>

#define MAGIC 0xd00dfeedu
#define VERSION 17u
#define COMPATIBLE_VERSION 16u
#define TOKEN_BEGIN_NODE 1u
#define TOKEN_END_NODE 2u
#define TOKEN_PROPERTY 3u
#define TOKEN_END 9u

static void require_space(size_t used, size_t extra, size_t capacity)
{
    if (extra > capacity - used) {
        abort();
    }
}

static void append_padded(struct device_tree_builder *builder, const void *bytes, size_t length)
{
    size_t padded = (length + 3u) & ~(size_t)3u;

    require_space(builder->structure_bytes, padded, BUILDER_STRUCTURE_CAPACITY);
    memset(builder->structure + builder->structure_bytes, 0, padded);
    if (length > 0) {
        memcpy(builder->structure + builder->structure_bytes, bytes, length);
    }
    builder->structure_bytes += padded;
}

static uint32_t intern_name(struct device_tree_builder *builder, const char *name)
{
    size_t length = strlen(name) + 1u;
    size_t offset = builder->strings_bytes;

    require_space(offset, length, BUILDER_STRINGS_CAPACITY);
    memcpy(builder->strings + offset, name, length);
    builder->strings_bytes += length;
    return (uint32_t)offset;
}

void blob_write_be32(uint8_t *blob, size_t offset, uint32_t value)
{
    blob[offset] = (uint8_t)(value >> 24);
    blob[offset + 1u] = (uint8_t)(value >> 16);
    blob[offset + 2u] = (uint8_t)(value >> 8);
    blob[offset + 3u] = (uint8_t)value;
}

uint32_t blob_read_be32(const uint8_t *blob, size_t offset)
{
    return ((uint32_t)blob[offset] << 24) | ((uint32_t)blob[offset + 1u] << 16) |
           ((uint32_t)blob[offset + 2u] << 8) | (uint32_t)blob[offset + 3u];
}

void builder_token(struct device_tree_builder *builder, uint32_t token)
{
    uint8_t encoded[4];

    blob_write_be32(encoded, 0, token);
    append_padded(builder, encoded, sizeof(encoded));
}

void builder_begin_node(struct device_tree_builder *builder, const char *name)
{
    builder_token(builder, TOKEN_BEGIN_NODE);
    append_padded(builder, name, strlen(name) + 1u);
}

void builder_end_node(struct device_tree_builder *builder)
{
    builder_token(builder, TOKEN_END_NODE);
}

void builder_property(struct device_tree_builder *builder, const char *name, const void *value,
                      size_t bytes)
{
    builder_token(builder, TOKEN_PROPERTY);
    builder_token(builder, (uint32_t)bytes);
    builder_token(builder, intern_name(builder, name));
    append_padded(builder, value, bytes);
}

void builder_cells(struct device_tree_builder *builder, const char *name, const uint32_t *cells,
                   size_t count)
{
    uint8_t encoded[64];

    require_space(0, count * 4u, sizeof(encoded));
    for (size_t index = 0; index < count; index++) {
        blob_write_be32(encoded, index * 4u, cells[index]);
    }
    builder_property(builder, name, encoded, count * 4u);
}

void builder_text(struct device_tree_builder *builder, const char *name, const char *text)
{
    builder_property(builder, name, text, strlen(text) + 1u);
}

void builder_reserve(struct device_tree_builder *builder, uint64_t base, uint64_t length)
{
    if (builder->reservation_count == BUILDER_RESERVATION_CAPACITY) {
        abort();
    }
    builder->reservations[2u * builder->reservation_count] = base;
    builder->reservations[2u * builder->reservation_count + 1u] = length;
    builder->reservation_count++;
}

size_t builder_finish(struct device_tree_builder *builder, uint8_t *blob, size_t capacity)
{
    builder_token(builder, TOKEN_END);

    size_t reservations_offset = BUILDER_HEADER_BYTES;
    size_t structure_offset = reservations_offset + (builder->reservation_count + 1u) * 16u;
    size_t strings_offset = structure_offset + builder->structure_bytes;
    size_t total = strings_offset + builder->strings_bytes;

    require_space(0, total, capacity);
    memset(blob, 0, total);
    blob_write_be32(blob, 0, MAGIC);
    blob_write_be32(blob, 4, (uint32_t)total);
    blob_write_be32(blob, 8, (uint32_t)structure_offset);
    blob_write_be32(blob, 12, (uint32_t)strings_offset);
    blob_write_be32(blob, 16, (uint32_t)reservations_offset);
    blob_write_be32(blob, 20, VERSION);
    blob_write_be32(blob, 24, COMPATIBLE_VERSION);
    blob_write_be32(blob, 32, (uint32_t)builder->strings_bytes);
    blob_write_be32(blob, 36, (uint32_t)builder->structure_bytes);

    for (size_t index = 0; index < 2u * builder->reservation_count; index++) {
        uint64_t value = builder->reservations[index];
        blob_write_be32(blob, reservations_offset + index * 8u, (uint32_t)(value >> 32));
        blob_write_be32(blob, reservations_offset + index * 8u + 4u, (uint32_t)value);
    }
    memcpy(blob + structure_offset, builder->structure, builder->structure_bytes);
    memcpy(blob + strings_offset, builder->strings, builder->strings_bytes);
    return total;
}
