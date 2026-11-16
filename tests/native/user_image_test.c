#include <stdint.h>
#include <string.h>

#include "check.h"
#include "kernel/abi/user_image.h"
#include "kernel/processes/user_image.h"

#define REGION_BASE 0x81000000ull
#define REGION_BYTES 0x800000ull
#define MODULE_BYTES 256u
#define FILE_BYTES 200ull
#define MEMORY_BYTES 0x3000ull
#define ENTRY_OFFSET 64ull
#define HEAP_BYTES 0x1000ull
#define STACK_BYTES 0x1000ull

#define FIELD_VERSION 4u
#define FIELD_LOAD_BASE 8u
#define FIELD_FILE_BYTES 16u
#define FIELD_MEMORY_BYTES 24u
#define FIELD_ENTRY 32u
#define FIELD_HEAP_BYTES 40u
#define FIELD_STACK_BYTES 48u

static const struct memory_range region = {.base = REGION_BASE, .length = REGION_BYTES};

static void write_field(uint8_t *module, size_t offset, size_t width, uint64_t value)
{
    for (size_t index = 0; index < width; index++) {
        module[offset + index] = (uint8_t)(value >> (index * 8u));
    }
}

static void build_module(uint8_t *module)
{
    memset(module, 0, MODULE_BYTES);
    write_field(module, 0, 4, USER_IMAGE_MAGIC);
    write_field(module, FIELD_VERSION, 4, USER_IMAGE_VERSION);
    write_field(module, FIELD_LOAD_BASE, 8, REGION_BASE);
    write_field(module, FIELD_FILE_BYTES, 8, FILE_BYTES);
    write_field(module, FIELD_MEMORY_BYTES, 8, MEMORY_BYTES);
    write_field(module, FIELD_ENTRY, 8, REGION_BASE + ENTRY_OFFSET);
    write_field(module, FIELD_HEAP_BYTES, 8, HEAP_BYTES);
    write_field(module, FIELD_STACK_BYTES, 8, STACK_BYTES);
}

static enum user_image_status parse_with(size_t offset, size_t width, uint64_t value)
{
    uint8_t module[MODULE_BYTES];
    struct user_image image;

    build_module(module);
    write_field(module, offset, width, value);
    return user_image_parse(module, MODULE_BYTES, region, &image);
}

static void test_valid_image_is_described(void)
{
    uint8_t module[MODULE_BYTES];
    struct user_image image = {0};

    build_module(module);
    CHECK(user_image_parse(module, MODULE_BYTES, region, &image) == USER_IMAGE_OK);
    CHECK(image.load_base == REGION_BASE);
    CHECK(image.file_bytes == FILE_BYTES);
    CHECK(image.memory_bytes == MEMORY_BYTES);
    CHECK(image.entry == REGION_BASE + ENTRY_OFFSET);
    CHECK(image.heap_bytes == HEAP_BYTES);
    CHECK(image.stack_bytes == STACK_BYTES);
}

static void test_header_must_be_complete_and_identified(void)
{
    uint8_t module[MODULE_BYTES];
    struct user_image image;

    build_module(module);
    CHECK(user_image_parse(module, USER_IMAGE_HEADER_BYTES - 1u, region, &image) ==
          USER_IMAGE_TRUNCATED_HEADER);
    CHECK(user_image_parse(module, 0, region, &image) == USER_IMAGE_TRUNCATED_HEADER);
    CHECK(parse_with(0, 4, USER_IMAGE_MAGIC + 1u) == USER_IMAGE_BAD_MAGIC);
    CHECK(parse_with(FIELD_VERSION, 4, USER_IMAGE_VERSION + 1u) == USER_IMAGE_UNSUPPORTED_VERSION);
}

static void test_segment_must_match_the_region(void)
{
    CHECK(parse_with(FIELD_LOAD_BASE, 8, REGION_BASE + 0x1000u) ==
          USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(FIELD_LOAD_BASE, 8, 0) == USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(FIELD_MEMORY_BYTES, 8, REGION_BYTES + 1u) ==
          USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(FIELD_MEMORY_BYTES, 8, UINT64_MAX) == USER_IMAGE_SEGMENT_OUTSIDE_REGION);
    CHECK(parse_with(FIELD_MEMORY_BYTES, 8, REGION_BYTES) == USER_IMAGE_OK);
}

static void test_file_size_is_bounded(void)
{
    CHECK(parse_with(FIELD_FILE_BYTES, 8, USER_IMAGE_HEADER_BYTES - 1u) ==
          USER_IMAGE_BAD_FILE_SIZE);
    CHECK(parse_with(FIELD_FILE_BYTES, 8, MODULE_BYTES + 1u) == USER_IMAGE_BAD_FILE_SIZE);
    CHECK(parse_with(FIELD_FILE_BYTES, 8, UINT64_MAX) == USER_IMAGE_BAD_FILE_SIZE);
    CHECK(parse_with(FIELD_MEMORY_BYTES, 8, FILE_BYTES - 1u) == USER_IMAGE_BAD_FILE_SIZE);
}

static void test_entry_must_be_code_inside_the_file(void)
{
    CHECK(parse_with(FIELD_ENTRY, 8, REGION_BASE + USER_IMAGE_HEADER_BYTES) == USER_IMAGE_OK);
    CHECK(parse_with(FIELD_ENTRY, 8, REGION_BASE + USER_IMAGE_HEADER_BYTES - 2u) ==
          USER_IMAGE_BAD_ENTRY);
    CHECK(parse_with(FIELD_ENTRY, 8, REGION_BASE + FILE_BYTES) == USER_IMAGE_BAD_ENTRY);
    CHECK(parse_with(FIELD_ENTRY, 8, REGION_BASE + ENTRY_OFFSET + 1u) == USER_IMAGE_BAD_ENTRY);
    CHECK(parse_with(FIELD_ENTRY, 8, REGION_BASE - 2u) == USER_IMAGE_BAD_ENTRY);
    CHECK(parse_with(FIELD_ENTRY, 8, 0) == USER_IMAGE_BAD_ENTRY);
}

static void test_reservations_fit_the_spare_memory(void)
{
    uint64_t spare = MEMORY_BYTES - FILE_BYTES;

    CHECK(parse_with(FIELD_HEAP_BYTES, 8, spare - STACK_BYTES) == USER_IMAGE_OK);
    CHECK(parse_with(FIELD_HEAP_BYTES, 8, spare - STACK_BYTES + 1u) ==
          USER_IMAGE_BAD_RESERVATION);
    CHECK(parse_with(FIELD_HEAP_BYTES, 8, UINT64_MAX) == USER_IMAGE_BAD_RESERVATION);
    CHECK(parse_with(FIELD_STACK_BYTES, 8, UINT64_MAX) == USER_IMAGE_BAD_RESERVATION);
}

static void test_rejection_leaves_the_output_untouched(void)
{
    uint8_t module[MODULE_BYTES];
    struct user_image image = {.entry = 7};

    build_module(module);
    write_field(module, FIELD_ENTRY, 8, 0);
    CHECK(user_image_parse(module, MODULE_BYTES, region, &image) == USER_IMAGE_BAD_ENTRY);
    CHECK(image.entry == 7);
}

static void test_every_status_has_a_name(void)
{
    CHECK(strcmp(user_image_status_name(USER_IMAGE_OK), "ok") == 0);
    CHECK(strcmp(user_image_status_name(USER_IMAGE_SEGMENT_OUTSIDE_REGION),
                 "segment-outside-region") == 0);
    CHECK(strcmp(user_image_status_name(USER_IMAGE_BAD_RESERVATION), "bad-reservation") == 0);
}

int main(void)
{
    test_valid_image_is_described();
    test_header_must_be_complete_and_identified();
    test_segment_must_match_the_region();
    test_file_size_is_bounded();
    test_entry_must_be_code_inside_the_file();
    test_reservations_fit_the_spare_memory();
    test_rejection_leaves_the_output_untouched();
    test_every_status_has_a_name();
    return check_finish("user-image");
}
