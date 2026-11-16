#include "kernel/ipc/call.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/rights.h"
#include "kernel/ipc/endpoint.h"
#include "kernel/objects/kernel_objects.h"

enum reply_state {
    REPLY_QUEUED,
    REPLY_DISPATCHED,
    REPLY_FINISHED,
};

static struct process *waiting_on(uint64_t reply, uint64_t caller_handle)
{
    struct process *caller = process_find(caller_handle);

    if (caller == NULL || caller->state != PROCESS_BLOCKED || caller->wait.kind != WAIT_REPLY ||
        caller->wait.object != reply) {
        return NULL;
    }
    return caller;
}

uint64_t call_reply_create(const struct process *caller, uint32_t endpoint)
{
    uint64_t reply =
        object_create(kernel_object_table(), OBJECT_REPLY, caller->index, caller->handle);
    struct kernel_object *object = object_find(kernel_object_table(), reply);

    if (object != NULL) {
        object->state = REPLY_QUEUED;
        object->detail = endpoint;
    }
    return reply;
}

void call_reply_discard(uint64_t reply)
{
    call_reply_finished(reply);
    object_release(kernel_object_table(), reply);
}

void call_reply_dispatched(uint64_t reply)
{
    struct kernel_object *object = object_find(kernel_object_table(), reply);

    if (object != NULL) {
        object->state = REPLY_DISPATCHED;
        object_release(kernel_object_table(), reply);
    }
}

void call_reply_finished(uint64_t reply)
{
    struct kernel_object *object = object_find(kernel_object_table(), reply);

    if (object != NULL) {
        object->state = REPLY_FINISHED;
    }
}

void call_reply_disposed(uint64_t reply, struct kernel_object object)
{
    struct process *caller;

    if (object.state != REPLY_DISPATCHED) {
        return;
    }
    caller = waiting_on(reply, object.payload);
    if (caller != NULL) {
        wait_complete(caller, -KERNEL_ERROR_PEER_CLOSED);
    }
}

struct process *call_waiting_caller(uint64_t reply)
{
    const struct kernel_object *object = object_find(kernel_object_table(), reply);

    if (object == NULL || object->state != REPLY_DISPATCHED) {
        return NULL;
    }
    return waiting_on(reply, object->payload);
}

void call_abandon(struct process *caller)
{
    uint64_t reply = caller->wait.object;
    struct kernel_object *object = object_find(kernel_object_table(), reply);

    if (object == NULL) {
        return;
    }
    if (object->state == REPLY_QUEUED) {
        object->state = REPLY_FINISHED;
        endpoint_remove_reply((uint32_t)object->detail, reply);
        object_release(kernel_object_table(), reply);
        return;
    }
    object->state = REPLY_FINISHED;
}

void call_peer_closed(uint64_t reply)
{
    const struct kernel_object *object = object_find(kernel_object_table(), reply);
    struct process *caller;

    if (object == NULL) {
        return;
    }
    caller = waiting_on(reply, object->payload);
    call_reply_discard(reply);
    if (caller != NULL) {
        wait_complete(caller, -KERNEL_ERROR_PEER_CLOSED);
    }
}
