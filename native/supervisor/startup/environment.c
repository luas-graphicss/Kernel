#include "kernel/startup/environment.h"

#include "kernel/devices/uart_ns16550.h"
#include "kernel/diagnostics/console.h"
#include "kernel/diagnostics/halt.h"
#include "kernel/memory/image.h"

static struct boot_environment environment;

static struct memory_range linked_range(const char *start, const char *end)
{
    return (struct memory_range){
        .base = (uint64_t)(uintptr_t)start,
        .length = (uint64_t)((uintptr_t)end - (uintptr_t)start),
    };
}

static void begin_rejection(const char *subject, const char *reason)
{
    console_text("boot:");
    console_field_text("rejected", subject);
    console_field_text("reason", reason);
}

static _Noreturn void finish_rejection(void)
{
    console_end_line();
    kernel_halt(false);
}

static void load_device_tree(const void *blob)
{
    struct device_tree tree;
    enum device_tree_status status = device_tree_open(blob, DEVICE_TREE_MAX_BYTES, &tree);

    if (status == DEVICE_TREE_OK) {
        status = device_tree_describe_boot(&tree, &environment.description);
    }
    if (status != DEVICE_TREE_OK) {
        begin_rejection("device-tree", device_tree_status_name(status));
        finish_rejection();
    }
    environment.device_tree = (struct memory_range){
        .base = (uint64_t)(uintptr_t)blob,
        .length = tree.total_bytes,
    };
}

static void attach_console(void)
{
    const struct memory_range *registers = &environment.description.console;

    if (registers->length < UART_NS16550_REGISTER_BYTES) {
        begin_rejection("console", "registers-too-small");
        finish_rejection();
    }
    console_attach_uart(registers->base);
}

static void begin_layout(void)
{
    struct memory_range ram = environment.description.memory;
    enum memory_layout_status status =
        memory_layout_begin(&environment.layout, ram, PROFILE_MEMORY_BYTES);

    if (status != MEMORY_LAYOUT_OK) {
        begin_rejection("memory", memory_layout_status_name(status));
        console_field_hex("available", ram.length);
        console_field_hex("required", PROFILE_MEMORY_BYTES);
        finish_rejection();
    }
}

static void reserve(const char *name, struct memory_range range)
{
    enum memory_layout_status status = memory_layout_reserve(&environment.layout, name, range);

    if (status == MEMORY_LAYOUT_OK) {
        return;
    }
    begin_rejection("memory", memory_layout_status_name(status));
    console_field_text("region", name);
    if (environment.layout.conflict != NULL) {
        console_field_text("conflict", environment.layout.conflict);
    }
    finish_rejection();
}

static void build_layout(void)
{
    const struct boot_description *description = &environment.description;

    environment.supervisor_heap = linked_range(supervisor_heap_start, supervisor_heap_end);
    environment.user_region = linked_range(user_region_start, user_region_end);

    begin_layout();
    for (size_t index = 0; index < description->reserved_count; index++) {
        reserve("firmware", description->reserved[index]);
    }
    reserve("kernel-image", linked_range(kernel_image_start, kernel_image_end));
    reserve("supervisor-stack", linked_range(supervisor_stack_bottom, supervisor_stack_top));
    reserve("emergency-stack", linked_range(emergency_stack_bottom, emergency_stack_top));
    reserve("supervisor-heap", environment.supervisor_heap);
    reserve("user-region", environment.user_region);
    reserve("device-tree", environment.device_tree);
    if (description->has_boot_module) {
        reserve("boot-module", description->boot_module);
    }
}

static void report(void)
{
    const struct memory_layout *layout = &environment.layout;

    console_text("boot:");
    console_field_decimal("hart", environment.hart);
    console_field_hex("device-tree", environment.device_tree.base);
    console_field_decimal("device-tree-bytes", environment.device_tree.length);
    console_field_decimal("device-tree-limit", DEVICE_TREE_MAX_BYTES);
    console_end_line();

    console_text("boot:");
    console_field_hex("memory", layout->ram.base);
    console_field_hex("bytes", layout->ram.length);
    console_end_line();

    for (size_t index = 0; index < layout->region_count; index++) {
        console_text("boot:");
        console_field_text("region", layout->regions[index].name);
        console_field_hex("base", layout->regions[index].range.base);
        console_field_hex("bytes", layout->regions[index].range.length);
        console_end_line();
    }

    console_text("boot:");
    console_field_text("console", "ns16550a");
    console_field_hex("registers", environment.description.console.base);
    console_end_line();
}

const struct boot_environment *boot_environment_load(uint64_t hart, const void *device_tree_blob)
{
    environment.hart = hart;
    load_device_tree(device_tree_blob);
    attach_console();
    build_layout();
    report();
    return &environment;
}

const struct boot_environment *boot_environment_current(void)
{
    return &environment;
}
