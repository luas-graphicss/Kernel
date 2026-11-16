#include "kernel/devices/device_registry.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/devices/device_inventory.h"
#include "kernel/devices/interrupt_controller.h"
#include "kernel/devices/interrupts.h"
#include "kernel/devices/serial_port.h"
#include "kernel/devices/virtio_mmio.h"
#include "kernel/diagnostics/console.h"
#include "kernel/diagnostics/halt.h"
#include "kernel/memory/endian.h"
#include "kernel/memory/kernel_space.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/objects/kernel_objects.h"

#define DEVICE_RIGHTS (RIGHT_READ | RIGHT_WRITE | RIGHT_ADMIN | RIGHT_DELEGATE)
#define UNCLAIMED_REFERENCES 1u
#define FIRST_TRANSPORT_SLOT 1u
#define QUEUE_FRAME_ORDER 0u
#define WORD_BYTES 4u
#define ANY_RIGHT 0u

static struct device_slot slots[DEVICE_SLOTS];
static uint64_t quarantined;

static uint32_t index_of(const struct device_slot *slot)
{
    return (uint32_t)(slot - slots);
}

static const char *kind_name(uint32_t kind)
{
    return kind == DEVICE_KIND_SERIAL ? "serial" : "virtio";
}

static void report_state(const struct device_slot *slot, const char *state)
{
    console_text("device:");
    console_field_decimal("slot", index_of(slot));
    console_field_text("state", state);
    console_field_text("reason", slot->virtio.failure != NULL ? slot->virtio.failure : "none");
    console_end_line();
}

static void wake(struct device_slot *slot)
{
    struct process *process = process_at(slot->waiter);

    slot->waiter = PROCESS_NONE;
    if (process != NULL && process->state == PROCESS_BLOCKED &&
        process->wait.kind == WAIT_DEVICE && process->wait.object == slot->object) {
        wait_restart(process);
    }
}

static void transport_interrupt(void *context)
{
    struct device_slot *slot = context;
    uint32_t before = slot->virtio.state;

    virtio_device_interrupt(&slot->virtio);
    if (before == DEVICE_STATE_READY && slot->virtio.state == DEVICE_STATE_FAILED) {
        report_state(slot, "failed");
    }
    wake(slot);
}

static void serial_interrupt(void *context)
{
    serial_port_receive();
    if (serial_port_has_input()) {
        wake(context);
    }
}

static void add_device(uint32_t index, uint32_t kind, uint32_t interrupt,
                       interrupt_handler handler)
{
    struct device_slot *slot = &slots[index];

    slot->object = object_create(kernel_object_table(), OBJECT_DEVICE, OBJECT_NO_OWNER, index);
    if (slot->object == SLOT_INVALID_HANDLE || !interrupts_bind(interrupt, handler, slot)) {
        kernel_panic("device-registration");
    }
    slot->present = true;
    slot->kind = kind;
    slot->interrupt = interrupt;
    console_text("boot:");
    console_field_decimal("device", index);
    console_field_text("kind", kind_name(kind));
    console_field_decimal("model", slot->virtio.model);
    console_field_decimal("interrupt", interrupt);
    console_end_line();
}

static bool is_isolated(const struct boot_environment *environment, struct memory_range registers)
{
    return registers.base % PAGE_BYTES == 0 &&
           !memory_ranges_overlap(environment->layout.ram, registers) &&
           !memory_ranges_overlap(environment->user_region, registers);
}

static bool attach_controller(const struct boot_environment *environment,
                              const struct interrupt_controller_description *controller)
{
    struct memory_range pages[INTERRUPT_CONTROLLER_PAGES];

    if (!controller->present || !is_isolated(environment, controller->registers) ||
        !interrupt_controller_pages(controller, pages)) {
        return false;
    }
    for (uint32_t page = 0; page < INTERRUPT_CONTROLLER_PAGES; page++) {
        if (!kernel_space_map_device(pages[page])) {
            return false;
        }
    }
    interrupts_attach(controller);
    return true;
}

static void add_serial(const struct boot_environment *environment,
                       const struct device_description *serial)
{
    if (serial->registers.base != environment->description.console.base) {
        return;
    }
    serial_port_attach(serial->registers.base);
    add_device(DEVICE_SERIAL_SLOT, DEVICE_KIND_SERIAL, serial->interrupt, serial_interrupt);
}

static void add_transport(const struct boot_environment *environment,
                          const struct device_description *transport, uint32_t index)
{
    struct memory_range registers = {.base = transport->registers.base, .length = PAGE_BYTES};
    uint64_t queue;

    if (transport->registers.length < VIRTIO_MMIO_REGISTER_BYTES ||
        !is_isolated(environment, registers) || !kernel_space_map_device(registers) ||
        virtio_device_identify((uintptr_t)registers.base) == 0) {
        return;
    }
    if (frame_pool_allocate(physical_memory_pool(), QUEUE_FRAME_ORDER, FRAME_FOR_SUPERVISOR,
                            &queue) != FRAME_OK) {
        kernel_panic("device-queue-memory");
    }
    virtio_device_attach(&slots[index].virtio, (uintptr_t)registers.base,
                         (void *)(uintptr_t)queue);
    add_device(index, DEVICE_KIND_VIRTIO, transport->interrupt, transport_interrupt);
}

static void reject(enum device_tree_status status)
{
    console_text("boot:");
    console_field_text("rejected", "devices");
    console_field_text("reason", device_tree_status_name(status));
    console_end_line();
    kernel_halt(false);
}

void device_registry_init(const struct boot_environment *environment)
{
    struct device_tree tree;
    struct device_inventory inventory;
    enum device_tree_status status = device_tree_open(
        (const void *)(uintptr_t)environment->device_tree.base, DEVICE_TREE_MAX_BYTES, &tree);

    quarantined = 0;
    for (uint32_t index = 0; index < DEVICE_SLOTS; index++) {
        slots[index] = (struct device_slot){.holder = PROCESS_NONE, .waiter = PROCESS_NONE};
    }
    if (status == DEVICE_TREE_OK) {
        status = device_tree_describe_devices(&tree, &inventory);
    }
    if (status != DEVICE_TREE_OK) {
        reject(status);
    }
    if (!attach_controller(environment, &inventory.controller)) {
        return;
    }
    if (inventory.has_serial) {
        add_serial(environment, &inventory.serial);
    }
    for (uint32_t index = 0; index < inventory.transport_count; index++) {
        add_transport(environment, &inventory.transports[index], FIRST_TRANSPORT_SLOT + index);
    }
}

struct device_slot *device_registry_slot(uint32_t index)
{
    return index < DEVICE_SLOTS && slots[index].present ? &slots[index] : NULL;
}

uint32_t device_registry_describe(uint8_t *entries)
{
    uint32_t count = 0;

    for (uint32_t index = 0; index < DEVICE_SLOTS; index++) {
        const struct device_slot *slot = &slots[index];
        uint8_t *entry = entries + count * DEVICE_ENTRY_BYTES;
        bool is_serial = slot->kind == DEVICE_KIND_SERIAL;

        if (!slot->present) {
            continue;
        }
        little_endian_write(entry + DEVICE_ENTRY_SLOT, WORD_BYTES, index);
        little_endian_write(entry + DEVICE_ENTRY_KIND, WORD_BYTES, slot->kind);
        little_endian_write(entry + DEVICE_ENTRY_MODEL, WORD_BYTES, slot->virtio.model);
        little_endian_write(entry + DEVICE_ENTRY_STATE, WORD_BYTES,
                            is_serial ? DEVICE_STATE_READY : slot->virtio.state);
        count++;
    }
    return count;
}

int64_t device_registry_claim(const struct process *caller, uint32_t index)
{
    const struct device_slot *slot = device_registry_slot(index);
    const struct kernel_object *object;
    int64_t handle;

    if (slot == NULL) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    object = object_find(kernel_object_table(), slot->object);
    if (object == NULL || object->references != UNCLAIMED_REFERENCES) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    object_retain(kernel_object_table(), slot->object);
    handle = capability_install(kernel_capabilities(), caller->index, slot->object, DEVICE_RIGHTS);
    if (handle < 0) {
        object_release(kernel_object_table(), slot->object);
    }
    return handle;
}

int64_t device_registry_open(struct device_slot *slot, const struct process *caller,
                             uint64_t features)
{
    int64_t status;

    if (slot->holder != PROCESS_NONE) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    status = virtio_device_open(&slot->virtio, features);
    if (status == KERNEL_OK) {
        slot->holder = caller->index;
        slot->holder_handle = caller->handle;
    }
    return status;
}

int64_t device_registry_close(struct device_slot *slot)
{
    uint32_t before = slot->virtio.state;
    int64_t status = virtio_device_reset(&slot->virtio);

    slot->holder = PROCESS_NONE;
    slot->holder_handle = 0;
    if (before != DEVICE_STATE_QUARANTINED && slot->virtio.state == DEVICE_STATE_QUARANTINED) {
        quarantined++;
        report_state(slot, "quarantined");
    }
    wake(slot);
    return status;
}

bool device_registry_holds(const struct device_slot *slot, const struct process *caller)
{
    return slot->holder == caller->index && slot->holder_handle == caller->handle;
}

void device_registry_await(struct device_slot *slot, struct process *caller, uint64_t deadline)
{
    wait_begin(caller, WAIT_DEVICE, true, slot->object, deadline, PROCESS_NONE);
    slot->waiter = caller->index;
}

void device_registry_capability_released(uint32_t space, uint64_t object)
{
    for (uint32_t index = 0; index < DEVICE_SLOTS; index++) {
        struct device_slot *slot = &slots[index];

        if (!slot->present || slot->object != object ||
            capability_space_holds(kernel_capabilities(), space, object, ANY_RIGHT)) {
            continue;
        }
        if (slot->waiter == space) {
            slot->waiter = PROCESS_NONE;
        }
        if (slot->holder == space) {
            device_registry_close(slot);
        }
    }
}

bool device_registry_has_waiters(void)
{
    for (uint32_t index = 0; index < process_capacity(); index++) {
        const struct process *process = process_at(index);

        if (process->state == PROCESS_BLOCKED && process->wait.kind == WAIT_DEVICE) {
            return true;
        }
    }
    return false;
}

uint64_t device_registry_requests(void)
{
    uint64_t requests = 0;

    for (uint32_t index = 0; index < DEVICE_SLOTS; index++) {
        if (slots[index].present && slots[index].kind == DEVICE_KIND_VIRTIO) {
            requests += virtio_device_in_flight(&slots[index].virtio);
        }
    }
    return requests;
}

uint64_t device_registry_quarantined(void)
{
    return quarantined;
}
