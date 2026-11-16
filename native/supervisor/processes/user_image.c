#include "kernel/processes/user_image.h"

#include <stddef.h>

#include "kernel/abi/user_image.h"
#include "kernel/memory/endian.h"
#include "kernel/memory/page_table.h"

#define WORD_BYTES 4u
#define DOUBLE_WORD_BYTES 8u
#define ODD_ADDRESS_MASK 1u
#define FIXED_TABLE_FRAMES 3u

static uint64_t double_word(const uint8_t *module, size_t offset)
{
    return little_endian_read(module + offset, DOUBLE_WORD_BYTES);
}

static struct user_image read_fields(const uint8_t *module)
{
    return (struct user_image){
        .load_base = double_word(module, USER_IMAGE_FIELD_LOAD_BASE),
        .file_bytes = double_word(module, USER_IMAGE_FIELD_FILE_BYTES),
        .entry = double_word(module, USER_IMAGE_FIELD_ENTRY),
        .text_bytes = double_word(module, USER_IMAGE_FIELD_TEXT_BYTES),
        .rodata_bytes = double_word(module, USER_IMAGE_FIELD_RODATA_BYTES),
        .data_bytes = double_word(module, USER_IMAGE_FIELD_DATA_BYTES),
        .heap_bytes = double_word(module, USER_IMAGE_FIELD_HEAP_BYTES),
        .stack_bytes = double_word(module, USER_IMAGE_FIELD_STACK_BYTES),
    };
}

static bool is_page_multiple(uint64_t bytes)
{
    return bytes % PAGE_BYTES == 0;
}

static bool take(uint64_t *remaining, uint64_t bytes)
{
    if (bytes > *remaining) {
        return false;
    }
    *remaining -= bytes;
    return true;
}

static bool extent_fits(const struct user_image *image, uint64_t heap_bytes, uint64_t limit)
{
    uint64_t remaining = limit;

    return take(&remaining, image->text_bytes) && take(&remaining, image->rodata_bytes) &&
           take(&remaining, image->data_bytes) && take(&remaining, heap_bytes) &&
           take(&remaining, USER_IMAGE_GUARD_BYTES) && take(&remaining, image->stack_bytes);
}

static enum user_image_status check_fields(const struct user_image *image, uint64_t module_bytes,
                                           struct memory_range region)
{
    uint64_t entry_offset;
    uint64_t executable_bytes;

    if (image->load_base != region.base) {
        return USER_IMAGE_SEGMENT_OUTSIDE_REGION;
    }
    if (image->text_bytes == 0 || !is_page_multiple(image->text_bytes) ||
        !is_page_multiple(image->rodata_bytes) || !is_page_multiple(image->data_bytes)) {
        return USER_IMAGE_BAD_SEGMENT;
    }
    if (image->heap_bytes == 0 || image->stack_bytes == 0 ||
        !is_page_multiple(image->heap_bytes) || !is_page_multiple(image->stack_bytes)) {
        return USER_IMAGE_BAD_RESERVATION;
    }
    if (!extent_fits(image, image->heap_bytes, region.length)) {
        return USER_IMAGE_SEGMENT_OUTSIDE_REGION;
    }
    if (image->file_bytes < USER_IMAGE_HEADER_BYTES || image->file_bytes > module_bytes ||
        image->file_bytes > image->text_bytes + image->rodata_bytes + image->data_bytes) {
        return USER_IMAGE_BAD_FILE_SIZE;
    }
    if (image->entry < image->load_base || (image->entry & ODD_ADDRESS_MASK) != 0) {
        return USER_IMAGE_BAD_ENTRY;
    }
    entry_offset = image->entry - image->load_base;
    executable_bytes = image->file_bytes < image->text_bytes ? image->file_bytes
                                                             : image->text_bytes;
    if (entry_offset < USER_IMAGE_HEADER_BYTES || entry_offset >= executable_bytes) {
        return USER_IMAGE_BAD_ENTRY;
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
    if (little_endian_read(module + USER_IMAGE_FIELD_MAGIC, WORD_BYTES) != USER_IMAGE_MAGIC) {
        return USER_IMAGE_BAD_MAGIC;
    }
    if (little_endian_read(module + USER_IMAGE_FIELD_VERSION, WORD_BYTES) != USER_IMAGE_VERSION) {
        return USER_IMAGE_UNSUPPORTED_VERSION;
    }
    parsed = read_fields(module);
    status = check_fields(&parsed, module_bytes, region);
    if (status == USER_IMAGE_OK) {
        *image = parsed;
    }
    return status;
}

bool user_layout_compute(const struct user_image *image, struct memory_range region,
                         uint64_t heap_bytes, struct user_layout *layout)
{
    uint64_t extent;

    if (heap_bytes == 0 || !is_page_multiple(heap_bytes) ||
        !extent_fits(image, heap_bytes, region.length)) {
        return false;
    }
    layout->text_base = image->load_base;
    layout->rodata_base = layout->text_base + image->text_bytes;
    layout->data_base = layout->rodata_base + image->rodata_bytes;
    layout->heap_base = layout->data_base + image->data_bytes;
    layout->heap_end = layout->heap_base + heap_bytes;
    layout->stack_bottom = layout->heap_end + USER_IMAGE_GUARD_BYTES;
    layout->stack_top = layout->stack_bottom + image->stack_bytes;
    layout->private_frames = (image->data_bytes + heap_bytes + image->stack_bytes) / PAGE_BYTES;
    extent = layout->stack_top - layout->text_base;
    layout->table_frames = FIXED_TABLE_FRAMES + extent / PAGE_LARGE_BYTES;
    return true;
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
    case USER_IMAGE_BAD_SEGMENT:
        return "bad-segment";
    case USER_IMAGE_BAD_FILE_SIZE:
        return "bad-file-size";
    case USER_IMAGE_BAD_ENTRY:
        return "bad-entry";
    case USER_IMAGE_BAD_RESERVATION:
        return "bad-reservation";
    }
    return "unknown";
}
