#include "kernel/processes/program.h"

#include <stdbool.h>
#include <stddef.h>

#include "kernel/memory/buffer.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/memory/string.h"
#include "kernel/startup/environment.h"

#define STATUS_READY "ok"
#define STATUS_ABSENT "absent"
#define STATUS_REGION_TOO_LARGE "user-region-too-large"
#define STATUS_OUT_OF_MEMORY "out-of-memory"

static struct {
    bool ready;
    struct user_image image;
    const uint8_t *module;
    uint64_t shared_base;
} program;

static uint64_t shared_bytes(const struct user_image *image)
{
    return image->text_bytes + image->rodata_bytes;
}

static bool copy_shared_pages(const struct user_image *image, const uint8_t *module)
{
    uint64_t bytes = shared_bytes(image);
    uint64_t copied = image->file_bytes < bytes ? image->file_bytes : bytes;
    uint8_t *destination;
    uint32_t order;

    if (!frame_order_for_bytes(bytes, &order) ||
        frame_pool_allocate(physical_memory_pool(), order, FRAME_FOR_SUPERVISOR,
                            &program.shared_base) != FRAME_OK) {
        return false;
    }
    destination = (uint8_t *)(uintptr_t)program.shared_base;
    memcpy(destination, module, (size_t)copied);
    memset(destination + copied, 0, (size_t)((FRAME_BYTES << order) - copied));
    return true;
}

const char *program_prepare(void)
{
    const struct boot_environment *environment = boot_environment_current();
    const struct memory_range module = environment->description.boot_module;
    struct user_image image;
    enum user_image_status status;

    if (program.ready) {
        return STATUS_READY;
    }
    if (!environment->description.has_boot_module) {
        return STATUS_ABSENT;
    }
    if (environment->user_region.length > BUFFER_WINDOW_OFFSET) {
        return STATUS_REGION_TOO_LARGE;
    }
    status = user_image_parse((const uint8_t *)(uintptr_t)module.base, module.length,
                              environment->user_region, &image);
    if (status != USER_IMAGE_OK) {
        return user_image_status_name(status);
    }
    if (!copy_shared_pages(&image, (const uint8_t *)(uintptr_t)module.base)) {
        return STATUS_OUT_OF_MEMORY;
    }
    program.image = image;
    program.module = (const uint8_t *)(uintptr_t)module.base;
    program.ready = true;
    return STATUS_READY;
}

const struct user_image *program_image(void)
{
    return program.ready ? &program.image : NULL;
}

struct memory_range program_region(void)
{
    return boot_environment_current()->user_region;
}

struct memory_range program_address_range(void)
{
    return (struct memory_range){
        .base = boot_environment_current()->user_region.base,
        .length = PAGE_ROOT_SPAN,
    };
}

enum page_status program_load(struct address_space *space, const struct user_layout *layout)
{
    const struct user_image *image = &program.image;
    uint64_t shared = shared_bytes(image);
    uint64_t writable = layout->heap_end - layout->data_base;
    enum page_status status;

    status = address_space_map_borrowed(space, layout->text_base, program.shared_base,
                                        image->text_bytes, PAGE_READ | PAGE_EXECUTE);
    if (status == PAGE_OK && image->rodata_bytes != 0) {
        status = address_space_map_borrowed(space, layout->rodata_base,
                                            program.shared_base + image->text_bytes,
                                            image->rodata_bytes, PAGE_READ);
    }
    if (status == PAGE_OK) {
        status = address_space_map_fresh(space, layout->data_base, writable,
                                         PAGE_READ | PAGE_WRITE);
    }
    if (status == PAGE_OK) {
        status = address_space_map_fresh(space, layout->stack_bottom,
                                         layout->stack_top - layout->stack_bottom,
                                         PAGE_READ | PAGE_WRITE);
    }
    if (status == PAGE_OK && image->file_bytes > shared &&
        !address_space_fill(space, layout->data_base, program.module + shared,
                            image->file_bytes - shared)) {
        status = PAGE_BAD_ADDRESS;
    }
    return status;
}
