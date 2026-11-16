#include "kernel/processes/user_image.h"

#include <stddef.h>

#include "kernel/abi/user_image.h"

#define FIELD_MAGIC 0u
#define FIELD_VERSION 4u
#define FIELD_LOAD_BASE 8u
#define FIELD_FILE_BYTES 16u
#define FIELD_MEMORY_BYTES 24u
#define FIELD_ENTRY 32u
#define FIELD_HEAP_BYTES 40u
#define FIELD_STACK_BYTES 48u
#define WORD_BYTES 4u
#define DOUBLE_WORD_BYTES 8u
#define BITS_PER_BYTE 8u
#define ODD_ADDRESS_MASK 1u

static uint64_t read_little_endian(const uint8_t *bytes, size_t width)
{
    uint64_t value = 0;

    for (size_t index = 0; index < width; index++) {
        value |= (uint64_t)bytes[index] << (index * BITS_PER_BYTE);
    }
    return value;
}

static struct user_image read_fields(const uint8_t *module)
{
    return (struct user_image){
        .load_base = read_little_endian(module + FIELD_LOAD_BASE, DOUBLE_WORD_BYTES),
        .file_bytes = read_little_endian(module + FIELD_FILE_BYTES, DOUBLE_WORD_BYTES),
        .memory_bytes = read_little_endian(module + FIELD_MEMORY_BYTES, DOUBLE_WORD_BYTES),
        .entry = read_little_endian(module + FIELD_ENTRY, DOUBLE_WORD_BYTES),
        .heap_bytes = read_little_endian(module + FIELD_HEAP_BYTES, DOUBLE_WORD_BYTES),
        .stack_bytes = read_little_endian(module + FIELD_STACK_BYTES, DOUBLE_WORD_BYTES),
    };
}

static enum user_image_status check_fields(const struct user_image *image, uint64_t module_bytes,
                                           struct memory_range region)
{
    uint64_t entry_offset;
    uint64_t spare_bytes;

    if (image->load_base != region.base || image->memory_bytes > region.length) {
        return USER_IMAGE_SEGMENT_OUTSIDE_REGION;
    }
    if (image->file_bytes < USER_IMAGE_HEADER_BYTES || image->file_bytes > module_bytes ||
        image->file_bytes > image->memory_bytes) {
        return USER_IMAGE_BAD_FILE_SIZE;
    }
    if (image->entry < image->load_base || (image->entry & ODD_ADDRESS_MASK) != 0) {
        return USER_IMAGE_BAD_ENTRY;
    }
    entry_offset = image->entry - image->load_base;
    if (entry_offset < USER_IMAGE_HEADER_BYTES || entry_offset >= image->file_bytes) {
        return USER_IMAGE_BAD_ENTRY;
    }
    spare_bytes = image->memory_bytes - image->file_bytes;
    if (image->heap_bytes > spare_bytes || image->stack_bytes > spare_bytes - image->heap_bytes) {
        return USER_IMAGE_BAD_RESERVATION;
    }
    return USER_IMAGE_OK;
}

enum user_image_status user_image_parse(const uint8_t *module, uint64_t module_bytes,
                                        struct memory_range region, struct user_image *image)
{
    struct user_image parsed;
    enum user_image_status status;

    if (module_bytes < USER_IMAGE_HEADER_BYTES) {
        return USER_IMAGE_TRUNCATED_HEADER;
    }
    if (read_little_endian(module + FIELD_MAGIC, WORD_BYTES) != USER_IMAGE_MAGIC) {
        return USER_IMAGE_BAD_MAGIC;
    }
    if (read_little_endian(module + FIELD_VERSION, WORD_BYTES) != USER_IMAGE_VERSION) {
        return USER_IMAGE_UNSUPPORTED_VERSION;
    }
    parsed = read_fields(module);
    status = check_fields(&parsed, module_bytes, region);
    if (status == USER_IMAGE_OK) {
        *image = parsed;
    }
    return status;
}

const char *user_image_status_name(enum user_image_status status)
{
    switch (status) {
    case USER_IMAGE_OK:
        return "ok";
    case USER_IMAGE_TRUNCATED_HEADER:
        return "truncated-header";
    case USER_IMAGE_BAD_MAGIC:
        return "bad-magic";
    case USER_IMAGE_UNSUPPORTED_VERSION:
        return "unsupported-version";
    case USER_IMAGE_SEGMENT_OUTSIDE_REGION:
        return "segment-outside-region";
    case USER_IMAGE_BAD_FILE_SIZE:
        return "bad-file-size";
    case USER_IMAGE_BAD_ENTRY:
        return "bad-entry";
    case USER_IMAGE_BAD_RESERVATION:
        return "bad-reservation";
    }
    return "unknown";
}
