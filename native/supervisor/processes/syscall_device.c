#include "kernel/processes/syscall.h"

#include <stddef.h>

#include "kernel/abi/devices.h"
#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/devices/device_registry.h"
#include "kernel/devices/serial_port.h"
#include "kernel/memory/endian.h"
#include "kernel/objects/kernel_objects.h"

#define WORD_BYTES 4u
#define DOUBLE_WORD_BYTES 8u
#define LIST_BYTES (DEVICE_SLOTS * DEVICE_ENTRY_BYTES)
#define COMPLETIONS_PER_WAIT 1

static int64_t require_system(const struct process *caller, uint64_t handle, uint32_t rights)
{
    struct capability capability;
    struct kernel_object *object;

    return capability_require(caller->index, handle, OBJECT_SYSTEM, rights, &capability, &object);
}

static int64_t require_device(const struct process *caller, uint64_t handle, uint32_t rights,
                              uint32_t kind, struct device_slot **slot)
{
    struct capability capability;
    struct kernel_object *object;
    int64_t status =
        capability_require(caller->index, handle, OBJECT_DEVICE, rights, &capability, &object);

    if (status != KERNEL_OK) {
        return status;
    }
    *slot = device_registry_slot((uint32_t)object->payload);
    if (*slot == NULL || (*slot)->kind != kind) {
        return -KERNEL_ERROR_UNSUPPORTED;
    }
    return KERNEL_OK;
}

static int64_t require_session(const struct process *caller, uint64_t handle, uint32_t rights,
                               struct device_slot **slot)
{
    int64_t status = require_device(caller, handle, rights, DEVICE_KIND_VIRTIO, slot);

    if (status == KERNEL_OK && !device_registry_holds(*slot, caller)) {
        return -KERNEL_ERROR_BAD_STATE;
    }
    return status;
}

static int64_t read_transfer(const struct process *caller, const uint8_t *segment,
                             struct virtio_transfer *transfer)
{
    struct capability capability;
    struct kernel_object *object;
    uint64_t flags = little_endian_read(segment + DEVICE_SEGMENT_FLAGS, WORD_BYTES);
    bool device_writes = (flags & DEVICE_SEGMENT_WRITABLE) != 0;
    int64_t status;

    if ((flags & ~(uint64_t)DEVICE_SEGMENT_WRITABLE) != 0 ||
        little_endian_read(segment + DEVICE_SEGMENT_RESERVED, WORD_BYTES) != 0) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    status = capability_require(
        caller->index, little_endian_read(segment + DEVICE_SEGMENT_BUFFER, DOUBLE_WORD_BYTES),
        OBJECT_BUFFER, device_writes ? RIGHT_WRITE : RIGHT_READ, &capability, &object);
    if (status != KERNEL_OK) {
        return status;
    }
    *transfer = (struct virtio_transfer){
        .buffer = (uint32_t)object->payload,
        .offset = (uint32_t)little_endian_read(segment + DEVICE_SEGMENT_OFFSET, WORD_BYTES),
        .length = (uint32_t)little_endian_read(segment + DEVICE_SEGMENT_LENGTH, WORD_BYTES),
        .device_writes = device_writes,
    };
    return KERNEL_OK;
}

struct syscall_result syscall_device_list(struct process *caller, const uint64_t *arguments)
{
    uint8_t entries[LIST_BYTES] = {0};
    uint32_t count;
    int64_t status = require_system(caller, arguments[0], RIGHT_READ);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (arguments[2] < LIST_BYTES) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    count = device_registry_describe(entries);
    if (!user_memory_write(&caller->space, arguments[1], entries, LIST_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    return syscall_resume(count);
}

struct syscall_result syscall_device_claim(struct process *caller, const uint64_t *arguments)
{
    int64_t status = require_system(caller, arguments[0], RIGHT_ADMIN);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (arguments[1] >= DEVICE_SLOTS) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    return syscall_resume(device_registry_claim(caller, (uint32_t)arguments[1]));
}

struct syscall_result syscall_device_open(struct process *caller, const uint64_t *arguments)
{
    uint8_t session[DEVICE_SESSION_BYTES] = {0};
    struct device_slot *slot;
    int64_t status =
        require_device(caller, arguments[0], RIGHT_ADMIN, DEVICE_KIND_VIRTIO, &slot);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if ((arguments[1] & ~DEVICE_FEATURE_MASK) != 0) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    if (!user_memory_is_writable(&caller->space, arguments[2], DEVICE_SESSION_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    status = device_registry_open(slot, caller, arguments[1]);
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    little_endian_write(session + DEVICE_SESSION_FEATURES, DOUBLE_WORD_BYTES,
                        slot->virtio.features & DEVICE_FEATURE_MASK);
    little_endian_write(session + DEVICE_SESSION_GENERATION, DOUBLE_WORD_BYTES,
                        slot->virtio.generation);
    little_endian_write(session + DEVICE_SESSION_QUEUE_SIZE, WORD_BYTES, DEVICE_QUEUE_SIZE);
    user_memory_write(&caller->space, arguments[2], session, DEVICE_SESSION_BYTES);
    return syscall_resume(KERNEL_OK);
}

struct syscall_result syscall_device_config(struct process *caller, const uint64_t *arguments)
{
    uint8_t bytes[DEVICE_CONFIG_BYTES];
    struct device_slot *slot;
    uint64_t offset = arguments[1];
    uint64_t length = arguments[3];
    int64_t status = require_session(caller, arguments[0], RIGHT_READ, &slot);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (length == 0 || offset > DEVICE_CONFIG_BYTES || length > DEVICE_CONFIG_BYTES - offset) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    status = virtio_device_read_config(&slot->virtio, (uint32_t)offset, bytes, (uint32_t)length);
    if (status < 0) {
        return syscall_resume(status);
    }
    if (!user_memory_write(&caller->space, arguments[2], bytes, length)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    return syscall_resume(status);
}

struct syscall_result syscall_device_submit(struct process *caller, const uint64_t *arguments)
{
    uint8_t request[DEVICE_REQUEST_BYTES];
    struct virtio_transfer transfers[DEVICE_SEGMENTS];
    struct device_slot *slot;
    uint64_t count;
    int64_t status = require_session(caller, arguments[0], RIGHT_WRITE, &slot);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (!user_memory_read(&caller->space, arguments[1], request, DEVICE_REQUEST_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    count = little_endian_read(request + DEVICE_REQUEST_SEGMENT_COUNT, WORD_BYTES);
    if (little_endian_read(request + DEVICE_REQUEST_QUEUE, WORD_BYTES) != 0 || count == 0 ||
        count > DEVICE_SEGMENTS) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    for (uint32_t index = 0; index < count; index++) {
        const uint8_t *segment = request + DEVICE_REQUEST_SEGMENTS + index * DEVICE_SEGMENT_BYTES;

        status = read_transfer(caller, segment, &transfers[index]);
        if (status != KERNEL_OK) {
            return syscall_resume(status);
        }
    }
    return syscall_resume(virtio_device_submit(&slot->virtio, transfers, (uint32_t)count));
}

struct syscall_result syscall_device_wait(struct process *caller, const uint64_t *arguments)
{
    uint8_t bytes[DEVICE_COMPLETION_BYTES] = {0};
    struct virtio_completion completion;
    struct device_slot *slot;
    uint64_t deadline;
    int64_t status = require_session(caller, arguments[0], RIGHT_READ, &slot);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (!user_memory_is_writable(&caller->space, arguments[1], DEVICE_COMPLETION_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    if (virtio_device_take_completion(&slot->virtio, &completion)) {
        little_endian_write(bytes + DEVICE_COMPLETION_TOKEN, DOUBLE_WORD_BYTES, completion.token);
        little_endian_write(bytes + DEVICE_COMPLETION_LENGTH, WORD_BYTES, completion.written);
        user_memory_write(&caller->space, arguments[1], bytes, DEVICE_COMPLETION_BYTES);
        return syscall_resume(COMPLETIONS_PER_WAIT);
    }
    if (slot->virtio.state != DEVICE_STATE_READY) {
        return syscall_resume(-KERNEL_ERROR_BAD_STATE);
    }
    if (!syscall_deadline(arguments[2], &deadline)) {
        return syscall_resume(-KERNEL_ERROR_TIMED_OUT);
    }
    device_registry_await(slot, caller, deadline);
    return syscall_block();
}

struct syscall_result syscall_device_reset(struct process *caller, const uint64_t *arguments)
{
    struct device_slot *slot;
    int64_t status =
        require_device(caller, arguments[0], RIGHT_ADMIN, DEVICE_KIND_VIRTIO, &slot);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    return syscall_resume(device_registry_close(slot));
}

struct syscall_result syscall_serial_write(struct process *caller, const uint64_t *arguments)
{
    uint8_t bytes[SERIAL_TRANSFER_BYTES];
    struct device_slot *slot;
    uint64_t length = arguments[2];
    int64_t status =
        require_device(caller, arguments[0], RIGHT_WRITE, DEVICE_KIND_SERIAL, &slot);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (length > SERIAL_TRANSFER_BYTES) {
        return syscall_resume(-KERNEL_ERROR_MESSAGE_TOO_LARGE);
    }
    if (length == 0) {
        return syscall_resume(0);
    }
    if (!user_memory_read(&caller->space, arguments[1], bytes, length)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    return syscall_resume(serial_port_write(bytes, (uint32_t)length));
}

struct syscall_result syscall_serial_read(struct process *caller, const uint64_t *arguments)
{
    uint8_t bytes[SERIAL_TRANSFER_BYTES];
    struct device_slot *slot;
    uint64_t capacity = arguments[2];
    uint64_t deadline;
    uint32_t count;
    int64_t status = require_device(caller, arguments[0], RIGHT_READ, DEVICE_KIND_SERIAL, &slot);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (capacity == 0 || capacity > SERIAL_TRANSFER_BYTES) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    if (!user_memory_is_writable(&caller->space, arguments[1], capacity)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    if (serial_port_has_input()) {
        count = serial_port_read(bytes, (uint32_t)capacity);
        user_memory_write(&caller->space, arguments[1], bytes, count);
        return syscall_resume(count);
    }
    if (!syscall_deadline(arguments[3], &deadline)) {
        return syscall_resume(-KERNEL_ERROR_TIMED_OUT);
    }
    device_registry_await(slot, caller, deadline);
    return syscall_block();
}
