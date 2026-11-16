#include "kernel/processes/syscall.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/ipc.h"
#include "kernel/abi/rights.h"
#include "kernel/ipc/call.h"
#include "kernel/ipc/endpoint.h"
#include "kernel/ipc/message.h"
#include "kernel/memory/endian.h"
#include "kernel/objects/kernel_objects.h"

#define DOUBLE_WORD_BYTES 8u

struct outgoing {
    uint32_t endpoint;
    uint32_t owner;
    uint32_t length;
    uint32_t transfer_rights;
    uint64_t transfer;
    struct ipc_header header;
};

static uint8_t scratch[IPC_MAX_MESSAGE_BYTES];

static int64_t read_message(const struct process *caller, uint64_t address, uint64_t length,
                            struct ipc_header *header)
{
    if (length < IPC_HEADER_BYTES) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    if (length > IPC_MAX_MESSAGE_BYTES) {
        return -KERNEL_ERROR_MESSAGE_TOO_LARGE;
    }
    if (!user_memory_read(&caller->space, address, scratch, length)) {
        return -KERNEL_ERROR_BAD_ADDRESS;
    }
    return ipc_message_parse(scratch, length, header);
}

static int64_t prepare(const struct process *caller, const uint64_t *arguments, uint64_t transfer,
                       struct outgoing *outgoing)
{
    struct capability capability;
    struct kernel_object *object;
    int64_t status = capability_require(caller->index, arguments[0], OBJECT_ENDPOINT, RIGHT_SEND,
                                        &capability, &object);

    if (status != KERNEL_OK) {
        return status;
    }
    outgoing->endpoint = (uint32_t)object->payload;
    if (!endpoint_is_open(outgoing->endpoint)) {
        return -KERNEL_ERROR_PEER_CLOSED;
    }
    outgoing->owner = endpoint_owner(outgoing->endpoint);
    status = read_message(caller, arguments[1], arguments[2], &outgoing->header);
    if (status != KERNEL_OK) {
        return status;
    }
    if ((outgoing->header.flags & IPC_FLAG_REPLY) != 0) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    outgoing->length = (uint32_t)arguments[2];
    outgoing->transfer = transfer;
    if (transfer == 0) {
        return KERNEL_OK;
    }
    return capability_transferable_rights(caller->index, transfer, &outgoing->transfer_rights);
}

static int64_t deliver(struct process *caller, const struct outgoing *outgoing, uint64_t reply)
{
    struct capability_registry *capabilities = kernel_capabilities();
    uint64_t transferred = 0;
    int64_t status;

    if (outgoing->transfer != 0) {
        status = capability_derive(capabilities, caller->index, outgoing->transfer,
                                   outgoing->transfer_rights, outgoing->owner);
        if (status < 0) {
            return status;
        }
        transferred = (uint64_t)status;
    }
    status =
        endpoint_enqueue(outgoing->endpoint, caller, scratch, outgoing->length, transferred, reply);
    if (status != KERNEL_OK) {
        if (transferred != 0) {
            capability_close(capabilities, outgoing->owner, transferred);
        }
        return status;
    }
    endpoint_wake_receiver(outgoing->endpoint);
    return KERNEL_OK;
}

static struct syscall_result wait_for_room(struct process *caller, const struct outgoing *outgoing,
                                           uint64_t deadline_nanoseconds)
{
    uint64_t deadline;
    int64_t status;

    if (outgoing->owner == caller->index) {
        return syscall_resume(-KERNEL_ERROR_WOULD_DEADLOCK);
    }
    if (!syscall_deadline(deadline_nanoseconds, &deadline)) {
        return syscall_resume(-KERNEL_ERROR_TIMED_OUT);
    }
    status = wait_chain_check(caller, outgoing->owner);
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    wait_begin(caller, WAIT_SEND, true, outgoing->endpoint, deadline, outgoing->owner);
    return syscall_block();
}

static void write_metadata(uint8_t *metadata, const struct ipc_delivery *delivery, uint64_t reply)
{
    little_endian_write(metadata + IPC_METADATA_SENDER, DOUBLE_WORD_BYTES, delivery->sender);
    little_endian_write(metadata + IPC_METADATA_TRANSFERRED, DOUBLE_WORD_BYTES,
                        delivery->transferred);
    little_endian_write(metadata + IPC_METADATA_REPLY, DOUBLE_WORD_BYTES, reply);
    little_endian_write(metadata + IPC_METADATA_LENGTH, DOUBLE_WORD_BYTES, delivery->length);
}

static int64_t accept_reply(const struct process *caller, uint64_t reply)
{
    int64_t handle;

    if (reply == 0) {
        return 0;
    }
    object_retain(kernel_object_table(), reply);
    handle = capability_install(kernel_capabilities(), caller->index, reply, RIGHT_SEND);
    if (handle < 0) {
        object_release(kernel_object_table(), reply);
        return handle;
    }
    call_reply_dispatched(reply);
    return handle;
}

struct syscall_result syscall_ipc_send(struct process *caller, const uint64_t *arguments)
{
    struct outgoing outgoing;
    int64_t status = prepare(caller, arguments, arguments[3], &outgoing);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (endpoint_is_full(outgoing.endpoint)) {
        return wait_for_room(caller, &outgoing, arguments[4]);
    }
    return syscall_resume(deliver(caller, &outgoing, 0));
}

struct syscall_result syscall_ipc_receive(struct process *caller, const uint64_t *arguments)
{
    uint8_t metadata[IPC_METADATA_BYTES];
    struct capability capability;
    struct kernel_object *object;
    struct ipc_delivery delivery;
    uint32_t endpoint;
    uint64_t deadline;
    int64_t reply;
    int64_t status = capability_require(caller->index, arguments[0], OBJECT_ENDPOINT,
                                        RIGHT_RECEIVE, &capability, &object);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    endpoint = (uint32_t)object->payload;
    if (endpoint_owner(endpoint) != caller->index) {
        return syscall_resume(-KERNEL_ERROR_ACCESS_DENIED);
    }
    if (!endpoint_peek(endpoint, &delivery)) {
        if (!syscall_deadline(arguments[4], &deadline)) {
            return syscall_resume(-KERNEL_ERROR_TIMED_OUT);
        }
        wait_begin(caller, WAIT_RECEIVE, true, endpoint, deadline, PROCESS_NONE);
        return syscall_block();
    }
    if (delivery.length > arguments[2]) {
        return syscall_resume(-KERNEL_ERROR_MESSAGE_TOO_LARGE);
    }
    if (!user_memory_is_writable(&caller->space, arguments[1], delivery.length) ||
        !user_memory_is_writable(&caller->space, arguments[3], IPC_METADATA_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    reply = accept_reply(caller, delivery.reply);
    if (reply < 0) {
        return syscall_resume(reply);
    }
    write_metadata(metadata, &delivery, (uint64_t)reply);
    user_memory_write(&caller->space, arguments[1], delivery.bytes, delivery.length);
    user_memory_write(&caller->space, arguments[3], metadata, IPC_METADATA_BYTES);
    endpoint_dequeue(endpoint);
    return syscall_resume((int64_t)delivery.length);
}

struct syscall_result syscall_ipc_call(struct process *caller, const uint64_t *arguments)
{
    uint8_t control[IPC_CALL_CONTROL_INPUT_BYTES];
    struct outgoing outgoing;
    uint64_t deadline;
    uint64_t reply;
    int64_t status;

    if (!user_memory_read(&caller->space, arguments[5], control, sizeof(control))) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    status = prepare(caller, arguments,
                     little_endian_read(control + IPC_CALL_TRANSFER, DOUBLE_WORD_BYTES), &outgoing);
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (!user_memory_is_writable(&caller->space, arguments[3], arguments[4]) ||
        !user_memory_is_writable(&caller->space, arguments[5], IPC_CALL_CONTROL_BYTES)) {
        return syscall_resume(-KERNEL_ERROR_BAD_ADDRESS);
    }
    if (outgoing.owner == caller->index) {
        return syscall_resume(-KERNEL_ERROR_WOULD_DEADLOCK);
    }
    status = wait_chain_check(caller, outgoing.owner);
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if (!syscall_deadline(little_endian_read(control + IPC_CALL_DEADLINE, DOUBLE_WORD_BYTES),
                          &deadline)) {
        return syscall_resume(-KERNEL_ERROR_TIMED_OUT);
    }
    if (endpoint_is_full(outgoing.endpoint)) {
        wait_begin(caller, WAIT_SEND, true, outgoing.endpoint, deadline, outgoing.owner);
        return syscall_block();
    }
    reply = call_reply_create(caller, outgoing.endpoint);
    if (reply == SLOT_INVALID_HANDLE) {
        return syscall_resume(-KERNEL_ERROR_LIMIT_EXCEEDED);
    }
    status = deliver(caller, &outgoing, reply);
    if (status != KERNEL_OK) {
        call_reply_discard(reply);
        return syscall_resume(status);
    }
    wait_begin(caller, WAIT_REPLY, false, reply, deadline, outgoing.owner);
    caller->wait.response_address = arguments[3];
    caller->wait.response_capacity = arguments[4];
    caller->wait.control_address = arguments[5];
    caller->wait.correlation = outgoing.header.correlation;
    return syscall_block();
}

static int64_t hand_over(struct process *waiting, uint64_t length, uint64_t received)
{
    uint8_t handle[DOUBLE_WORD_BYTES];
    uint64_t slot = waiting->wait.control_address + IPC_CALL_RECEIVED;

    little_endian_write(handle, DOUBLE_WORD_BYTES, received);
    if (!user_memory_is_writable(&waiting->space, waiting->wait.response_address, length) ||
        !user_memory_is_writable(&waiting->space, slot, DOUBLE_WORD_BYTES)) {
        if (received != 0) {
            capability_close(kernel_capabilities(), waiting->index, received);
        }
        return -KERNEL_ERROR_BAD_ADDRESS;
    }
    user_memory_write(&waiting->space, waiting->wait.response_address, scratch, length);
    user_memory_write(&waiting->space, slot, handle, DOUBLE_WORD_BYTES);
    return (int64_t)length;
}

static int64_t transfer_to(const struct process *caller, uint64_t transfer,
                           const struct process *waiting)
{
    uint32_t rights;
    int64_t status;

    if (transfer == 0) {
        return 0;
    }
    status = capability_transferable_rights(caller->index, transfer, &rights);
    if (status != KERNEL_OK) {
        return status;
    }
    return capability_derive(kernel_capabilities(), caller->index, transfer, rights,
                             waiting->index);
}

struct syscall_result syscall_ipc_reply(struct process *caller, const uint64_t *arguments)
{
    struct capability capability;
    struct kernel_object *object;
    struct process *waiting;
    struct ipc_header header;
    int64_t received;
    int64_t status =
        capability_require(caller->index, arguments[0], OBJECT_REPLY, RIGHT_SEND, &capability,
                           &object);

    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    waiting = call_waiting_caller(capability.object);
    if (waiting == NULL) {
        capability_close(kernel_capabilities(), caller->index, arguments[0]);
        return syscall_resume(-KERNEL_ERROR_PEER_CLOSED);
    }
    status = read_message(caller, arguments[1], arguments[2], &header);
    if (status != KERNEL_OK) {
        return syscall_resume(status);
    }
    if ((header.flags & IPC_FLAG_REPLY) == 0 || header.correlation != waiting->wait.correlation) {
        return syscall_resume(-KERNEL_ERROR_INVALID_ARGUMENT);
    }
    if (arguments[2] > waiting->wait.response_capacity) {
        return syscall_resume(-KERNEL_ERROR_MESSAGE_TOO_LARGE);
    }
    received = transfer_to(caller, arguments[3], waiting);
    if (received < 0) {
        return syscall_resume(received);
    }
    status = hand_over(waiting, arguments[2], (uint64_t)received);
    call_reply_finished(capability.object);
    wait_complete(waiting, status);
    capability_close(kernel_capabilities(), caller->index, arguments[0]);
    return syscall_resume(KERNEL_OK);
}
