#include "kernel/devices/device_inventory.h"
#include "kernel/devices/device_tree.h"
#include "kernel/processes/user_image.h"
#include "targets.h"

#define USER_REGION_BASE 0x40000000ull
#define USER_REGION_BYTES 0x1000000ull
#define STATUS_BITS 8

static size_t length_up_to(const char *text, size_t limit)
{
    size_t length = 0;

    while (length <= limit && text[length] != '\0') {
        length++;
    }
    return length;
}

int64_t fuzz_device_tree(const uint8_t *data, size_t length)
{
    struct device_tree tree;
    struct boot_description description;
    struct device_inventory inventory;
    enum device_tree_status opened = device_tree_open(data, length, &tree);
    enum device_tree_status described;
    enum device_tree_status listed;

    if (opened != DEVICE_TREE_OK) {
        return (int64_t)opened;
    }
    FUZZ_REQUIRE(tree.total_bytes <= length);
    described = device_tree_describe_boot(&tree, &description);
    if (described == DEVICE_TREE_OK) {
        FUZZ_REQUIRE(description.reserved_count <= DEVICE_TREE_MAX_RESERVATIONS);
        FUZZ_REQUIRE(description.arguments == NULL ||
                     length_up_to(description.arguments, DEVICE_TREE_MAX_ARGUMENT_BYTES) <=
                         DEVICE_TREE_MAX_ARGUMENT_BYTES);
    }
    listed = device_tree_describe_devices(&tree, &inventory);
    if (listed == DEVICE_TREE_OK) {
        FUZZ_REQUIRE(inventory.transport_count <= DEVICE_TRANSPORTS);
    }
    return ((int64_t)described << STATUS_BITS) | (int64_t)listed;
}

int64_t fuzz_user_image(const uint8_t *data, size_t length)
{
    const struct memory_range region = {.base = USER_REGION_BASE, .length = USER_REGION_BYTES};
    struct user_image image;
    struct user_layout layout;
    enum user_image_status status = user_image_parse(data, length, region, &image);

    if (status != USER_IMAGE_OK) {
        return (int64_t)status;
    }
    FUZZ_REQUIRE(image.file_bytes <= length);
    if (user_layout_compute(&image, region, image.heap_bytes, &layout)) {
        FUZZ_REQUIRE(layout.text_base >= region.base);
        FUZZ_REQUIRE(layout.text_base <= layout.rodata_base);
        FUZZ_REQUIRE(layout.rodata_base <= layout.data_base);
        FUZZ_REQUIRE(layout.data_base <= layout.heap_base);
        FUZZ_REQUIRE(layout.heap_base <= layout.heap_end);
        FUZZ_REQUIRE(layout.heap_end <= layout.stack_bottom);
        FUZZ_REQUIRE(layout.stack_bottom <= layout.stack_top);
        FUZZ_REQUIRE(layout.stack_top <= region.base + region.length);
    }
    return 0;
}
