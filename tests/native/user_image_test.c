#include <stdint.h>
#include <string.h>

#include "check.h"
#include "kernel/abi/user_image.h"
#include "kernel/memory/endian.h"
#include "kernel/memory/page_table.h"
#include "kernel/processes/user_image.h"

#define REGION_BASE 0x40000000ull
#define REGION_BYTES 0x1000000ull
#define MODULE_BYTES 0x3000u
#define FILE_BYTES 0x2800ull
#define TEXT_BYTES 0x1000ull
#define RODATA_BYTES 0x1000ull
#define DATA_BYTES 0x2000ull
#define HEAP_BYTES 0x4000ull
#define STACK_BYTES 0x2000ull
#define ENTRY_OFFSET 0x80ull

static const struct memory_range region = {.base = REGION_BASE, .length = REGION_BYTES};
static uint8_t module[MODULE_BYTES];

static void build_module(void)
{
    memset(module, 0, MODULE_BYTES);
    little_endian_write(module + USER_IMAGE_FIELD_MAGIC, 4, USER_IMAGE_MAGIC);
    little_endian_write(module + USER_IMAGE_FIELD_VERSION, 4, USER_IMAGE_VERSION);
    little_endian_write(module + USER_IMAGE_FIELD_LOAD_BASE, 8, REGION_BASE);
    little_endian_write(module + USER_IMAGE_FIELD_FILE_BYTES, 8, FILE_BYTES);
    little_endian_write(module + USER_IMAGE_FIELD_ENTRY, 8, REGION_BASE + ENTRY_OFFSET);
    little_endian_write(module + USER_IMAGE_FIELD_TEXT_BYTES, 8, TEXT_BYTES);
    little_endian_write(module + USER_IMAGE_FIELD_RODATA_BYTES, 8, RODATA_BYTES);
    little_endian_write(module + USER_IMAGE_FIELD_DATA_BYTES, 8, DATA_BYTES);
    little_endian_write(module + USER_IMAGE_FIELD_HEAP_BYTES, 8, HEAP_BYTES);
    little_endian_write(module + USER_IMAGE_FIELD_STACK_BYTES, 8, STACK_BYTES);
}

static enum user_image_status parse_with(size_t offset, size_t width, uint64_t value)
{
    struct user_image image;

    build_module();
    little_endian_write(module + offset, width, value);
    return user_image_parse(module, MODULE_BYTES, region, &image);
}

static struct user_image valid_image(void)
{
    struct user_image image = {0};

    build_module();
    CHECK(user_image_parse(module, MODULE_BYTES, region, &image) == USER_IMAGE_OK);
    return image;
}

static void test_valid_image_is_described(void)
{
    struct user_image image = valid_image();

    CHECK(image.load_base == REGION_BASE);
    CHECK(image.file_bytes == FILE_BYTES);
    CHECK(image.entry == REGION_BASE + ENTRY_OFFSET);
    CHECK(image.text_bytes == TEXT_BYTES && image.rodata_bytes == RODATA_BYTES);
    CHECK(image.data_bytes == DATA_BYTES);
    CHECK(image.heap_bytes == HEAP_BYTES && image.stack_bytes == STACK_BYTES);
}

static void test_header_must_be_complete_and_identified(void)
{
    struct user_image image;

    build_module();
    CHECK(user_image_parse(module, USER_IMAGE_HEADER_BYTES - 1u, region, &image) ==
          USER_IMAGE_TRUNCATED_HEADER);
    CHECK(user_image_parse(module, 0, region, &image) == USER_IMAGE_TRUNCATED_HEADER);
    CHECK(parse_with(USER_IMAGE_FIELD_MAGIC, 4, USER_IMAGE_MAGIC + 1u) == USER_IMAGE_BAD_MAGIC);
    CHECK(parse_with(USER_IMAGE_FIELD_VERSION, 4, USER_IMAGE_VERSION + 1u) ==
          USER_IMAGE_UNSUPPORTED_VERSION);
    CHECK(parse_with(USER_IMAGE_FIELD_VERSION, 4, 1) == USER_IMAGE_UNSUPPORTED_VERSION);
}

static void test_image_must_fit_the_user_region(void)
{
    CHECK(parse_with(USER_IMAGE_FIELD_LOAD_BASE, 8, REGION_BASE + 0x1000u) ==
          USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(USER_IMAGE_FIELD_LOAD_BASE, 8, 0) == USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(USER_IMAGE_FIELD_HEAP_BYTES, 8, REGION_BYTES) ==
          USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(USER_IMAGE_FIELD_STACK_BYTES, 8, UINT64_MAX - PAGE_BYTES + 1u) ==
          USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(USER_IMAGE_FIELD_DATA_BYTES, 8, UINT64_MAX - PAGE_BYTES + 1u) ==
          USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(USER_IMAGE_FIELD_HEAP_BYTES, 8,
                     REGION_BYTES - TEXT_BYTES - RODATA_BYTES - DATA_BYTES - STACK_BYTES -
                         USER_IMAGE_GUARD_BYTES) == USER_IMAGE_OK);
    CHECK(parse_with(USER_IMAGE_FIELD_HEAP_BYTES, 8,
                     REGION_BYTES - TEXT_BYTES - RODATA_BYTES - DATA_BYTES - STACK_BYTES) ==
          USER_IMAGE_SEGMENT_OUTSIDE_REGION);
}

static void test_segments_are_whole_pages(void)
{
    CHECK(parse_with(USER_IMAGE_FIELD_TEXT_BYTES, 8, 0) == USER_IMAGE_BAD_SEGMENT);
    CHECK(parse_with(USER_IMAGE_FIELD_TEXT_BYTES, 8, TEXT_BYTES + 1u) == USER_IMAGE_BAD_SEGMENT);
    CHECK(parse_with(USER_IMAGE_FIELD_RODATA_BYTES, 8, RODATA_BYTES - 8u) ==
          USER_IMAGE_BAD_SEGMENT);
    CHECK(parse_with(USER_IMAGE_FIELD_DATA_BYTES, 8, DATA_BYTES + 0x800u) ==
          USER_IMAGE_BAD_SEGMENT);
    CHECK(parse_with(USER_IMAGE_FIELD_HEAP_BYTES, 8, 0) == USER_IMAGE_BAD_RESERVATION);
    CHECK(parse_with(USER_IMAGE_FIELD_HEAP_BYTES, 8, HEAP_BYTES + 1u) ==
          USER_IMAGE_BAD_RESERVATION);
    CHECK(parse_with(USER_IMAGE_FIELD_STACK_BYTES, 8, 0) == USER_IMAGE_BAD_RESERVATION);
    CHECK(parse_with(USER_IMAGE_FIELD_STACK_BYTES, 8, STACK_BYTES - 1u) ==
          USER_IMAGE_BAD_RESERVATION);
}

static void test_file_size_is_bounded(void)
{
    CHECK(parse_with(USER_IMAGE_FIELD_FILE_BYTES, 8, USER_IMAGE_HEADER_BYTES - 1u) ==
          USER_IMAGE_BAD_FILE_SIZE);
    CHECK(parse_with(USER_IMAGE_FIELD_FILE_BYTES, 8, MODULE_BYTES + 1u) ==
          USER_IMAGE_BAD_FILE_SIZE);
    CHECK(parse_with(USER_IMAGE_FIELD_FILE_BYTES, 8, UINT64_MAX) == USER_IMAGE_BAD_FILE_SIZE);
    CHECK(parse_with(USER_IMAGE_FIELD_DATA_BYTES, 8, 0) == USER_IMAGE_BAD_FILE_SIZE);
    CHECK(parse_with(USER_IMAGE_FIELD_FILE_BYTES, 8, MODULE_BYTES) == USER_IMAGE_OK);
}

static void test_entry_must_be_code_inside_the_text(void)
{
    CHECK(parse_with(USER_IMAGE_FIELD_ENTRY, 8, REGION_BASE + USER_IMAGE_HEADER_BYTES) ==
          USER_IMAGE_OK);
    CHECK(parse_with(USER_IMAGE_FIELD_ENTRY, 8, REGION_BASE + USER_IMAGE_HEADER_BYTES - 2u) ==
          USER_IMAGE_BAD_ENTRY);
    CHECK(parse_with(USER_IMAGE_FIELD_ENTRY, 8, REGION_BASE + TEXT_BYTES - 2u) == USER_IMAGE_OK);
    CHECK(parse_with(USER_IMAGE_FIELD_ENTRY, 8, REGION_BASE + TEXT_BYTES) == USER_IMAGE_BAD_ENTRY);
    CHECK(parse_with(USER_IMAGE_FIELD_ENTRY, 8, REGION_BASE + ENTRY_OFFSET + 1u) ==
          USER_IMAGE_BAD_ENTRY);
    CHECK(parse_with(USER_IMAGE_FIELD_ENTRY, 8, REGION_BASE - 2u) == USER_IMAGE_BAD_ENTRY);
    CHECK(parse_with(USER_IMAGE_FIELD_ENTRY, 8, 0) == USER_IMAGE_BAD_ENTRY);
}

static void test_rejection_leaves_the_output_untouched(void)
{
    struct user_image image = {.entry = 7};

    build_module();
    little_endian_write(module + USER_IMAGE_FIELD_ENTRY, 8, 0);
    CHECK(user_image_parse(module, MODULE_BYTES, region, &image) == USER_IMAGE_BAD_ENTRY);
    CHECK(image.entry == 7);
}

static void test_layout_separates_the_stack_with_a_guard(void)
{
    struct user_image image = valid_image();
    struct user_layout layout = {0};

    CHECK(user_layout_compute(&image, region, 0x8000, &layout));
    CHECK(layout.text_base == REGION_BASE);
    CHECK(layout.rodata_base == REGION_BASE + TEXT_BYTES);
    CHECK(layout.data_base == layout.rodata_base + RODATA_BYTES);
    CHECK(layout.heap_base == layout.data_base + DATA_BYTES);
    CHECK(layout.heap_end == layout.heap_base + 0x8000u);
    CHECK(layout.stack_bottom == layout.heap_end + USER_IMAGE_GUARD_BYTES);
    CHECK(layout.stack_top == layout.stack_bottom + STACK_BYTES);
    CHECK(layout.private_frames == (DATA_BYTES + 0x8000u + STACK_BYTES) / PAGE_BYTES);
    CHECK(layout.table_frames >= 3);

    CHECK(!user_layout_compute(&image, region, 0, &layout));
    CHECK(!user_layout_compute(&image, region, 0x8001, &layout));
    CHECK(!user_layout_compute(&image, region, REGION_BYTES, &layout));
    CHECK(!user_layout_compute(&image, region, UINT64_MAX - PAGE_BYTES + 1u, &layout));
}

static void test_every_status_has_a_name(void)
{
    CHECK(strcmp(user_image_status_name(USER_IMAGE_OK), "ok") == 0);
    CHECK(strcmp(user_image_status_name(USER_IMAGE_SEGMENT_OUTSIDE_REGION),
                 "segment-outside-region") == 0);
    CHECK(strcmp(user_image_status_name(USER_IMAGE_BAD_SEGMENT), "bad-segment") == 0);
    CHECK(strcmp(user_image_status_name(USER_IMAGE_BAD_RESERVATION), "bad-reservation") == 0);
}

int main(void)
{
    test_valid_image_is_described();
    test_header_must_be_complete_and_identified();
    test_image_must_fit_the_user_region();
    test_segments_are_whole_pages();
    test_file_size_is_bounded();
    test_entry_must_be_code_inside_the_text();
    test_rejection_leaves_the_output_untouched();
    test_layout_separates_the_stack_with_a_guard();
    test_every_status_has_a_name();
    return check_finish("user-image");
}
