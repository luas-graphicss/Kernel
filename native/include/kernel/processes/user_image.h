#ifndef KERNEL_PROCESSES_USER_IMAGE_H
#define KERNEL_PROCESSES_USER_IMAGE_H

#include <stdint.h>

#include "kernel/memory/range.h"

enum user_image_status {
    USER_IMAGE_OK,
    USER_IMAGE_TRUNCATED_HEADER,
    USER_IMAGE_BAD_MAGIC,
    USER_IMAGE_UNSUPPORTED_VERSION,
    USER_IMAGE_SEGMENT_OUTSIDE_REGION,
    USER_IMAGE_BAD_FILE_SIZE,
    USER_IMAGE_BAD_ENTRY,
    USER_IMAGE_BAD_RESERVATION,
};

struct user_image {
    uint64_t load_base;
    uint64_t file_bytes;
    uint64_t memory_bytes;
    uint64_t entry;
    uint64_t heap_bytes;
    uint64_t stack_bytes;
};

enum user_image_status user_image_parse(const uint8_t *module, uint64_t module_bytes,
                                        struct memory_range region, struct user_image *image);
const char *user_image_status_name(enum user_image_status status);

#endif
