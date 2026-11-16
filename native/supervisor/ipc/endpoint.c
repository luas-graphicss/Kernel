#include "kernel/ipc/endpoint.h"

#include <stddef.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/ipc.h"
#include "kernel/ipc/call.h"
#include "kernel/memory/physical_memory.h"
#include "kernel/memory/string.h"
#include "kernel/objects/kernel_objects.h"

#define ENDPOINT_CAPACITY 128u
#define MESSAGE_CAPACITY 1024u
#define NO_MESSAGE UINT32_MAX
#define LARGE_MESSAGE_ORDER 1u

struct endpoint {
    bool used;
    bool open;
    uint32_t owner;
    uint32_t head;
    uint32_t tail;
    uint32_t count;
};

struct queued_message {
    uint32_t next;
    uint32_t length;
    uint32_t order;
    uint32_t sender;
    uint64_t sender_handle;
    uint64_t frame;
    uint64_t transferred;
    uint64_t reply;
};

static struct endpoint endpoints[ENDPOINT_CAPACITY];
static struct queued_message messages[MESSAGE_CAPACITY];
static uint32_t free_message;
static struct ipc_usage usage;

static uint32_t message_order(uint32_t length)
{
    return length > FRAME_BYTES ? LARGE_MESSAGE_ORDER : 0;
}

static uint64_t message_bytes(const struct queued_message *message)
{
    return FRAME_BYTES << message->order;
}

static void release_message(uint32_t index)
{
    struct queued_message *message = &messages[index];
    struct process *sender = process_at(message->sender);

    if (sender != NULL && sender->handle == message->sender_handle) {
        sender->ipc_pending_bytes -= message_bytes(message);
    }
    usage.pending_bytes -= message_bytes(message);
    usage.messages--;
    frame_pool_free(physical_memory_pool(), message->frame, message->order);
    message->next = free_message;
    free_message = index;
}

static uint32_t unlink_head(struct endpoint *endpoint)
{
    uint32_t index = endpoint->head;

    endpoint->head = messages[index].next;
    if (endpoint->head == NO_MESSAGE) {
        endpoint->tail = NO_MESSAGE;
    }
    endpoint->count--;
    return index;
}

static void wake_sender(uint32_t endpoint)
{
    struct process *oldest = NULL;

    for (uint32_t index = 0; index < process_capacity(); index++) {
        struct process *process = process_at(index);

        if (process->state == PROCESS_BLOCKED && process->wait.kind == WAIT_SEND &&
            process->wait.object == endpoint &&
            (oldest == NULL || process->wait.sequence < oldest->wait.sequence)) {
            oldest = process;
        }
    }
    if (oldest != NULL) {
        wait_restart(oldest);
    }
}

static void fail_senders(uint32_t endpoint)
{
    for (uint32_t index = 0; index < process_capacity(); index++) {
        struct process *process = process_at(index);

        if (process->state == PROCESS_BLOCKED && process->wait.kind == WAIT_SEND &&
            process->wait.object == endpoint) {
            wait_finish(process, -KERNEL_ERROR_PEER_CLOSED);
        }
    }
}

static void drop_message(const struct endpoint *endpoint, uint32_t index)
{
    uint64_t transferred = messages[index].transferred;
    uint64_t reply = messages[index].reply;

    release_message(index);
    if (transferred != 0) {
        capability_close(kernel_capabilities(), endpoint->owner, transferred);
    }
    if (reply != 0) {
        call_peer_closed(reply);
    }
}

void endpoint_table_init(void)
{
    free_message = NO_MESSAGE;
    for (uint32_t index = MESSAGE_CAPACITY; index > 0; index--) {
        messages[index - 1u].next = free_message;
        free_message = index - 1u;
    }
    usage = (struct ipc_usage){0};
}

int64_t endpoint_allocate(uint32_t owner)
{
    for (uint32_t index = 0; index < ENDPOINT_CAPACITY; index++) {
        if (!endpoints[index].used) {
            endpoints[index] = (struct endpoint){
                .used = true,
                .open = true,
                .owner = owner,
                .head = NO_MESSAGE,
                .tail = NO_MESSAGE,
            };
            usage.endpoints++;
            return index;
        }
    }
    return -KERNEL_ERROR_LIMIT_EXCEEDED;
}

void endpoint_close(uint32_t index)
{
    struct endpoint *endpoint = &endpoints[index];

    if (!endpoint->used || !endpoint->open) {
        return;
    }
    endpoint->open = false;
    while (endpoint->head != NO_MESSAGE) {
        drop_message(endpoint, unlink_head(endpoint));
    }
    fail_senders(index);
}

void endpoint_dispose(uint32_t index)
{
    if (!endpoints[index].used) {
        return;
    }
    endpoint_close(index);
    endpoints[index].used = false;
    usage.endpoints--;
}

bool endpoint_is_open(uint32_t endpoint)
{
    return endpoints[endpoint].used && endpoints[endpoint].open;
}

bool endpoint_is_full(uint32_t endpoint)
{
    return endpoints[endpoint].count >= IPC_ENDPOINT_MESSAGES;
}

uint32_t endpoint_owner(uint32_t endpoint)
{
    return endpoints[endpoint].owner;
}

int64_t endpoint_enqueue(uint32_t index, struct process *sender, const uint8_t *bytes,
                         uint32_t length, uint64_t transferred, uint64_t reply)
{
    struct endpoint *endpoint = &endpoints[index];
    uint32_t order = message_order(length);
    uint64_t charged = FRAME_BYTES << order;
    struct queued_message *message;
    uint32_t slot = free_message;
    uint64_t frame;

    if (sender->ipc_pending_bytes + charged > sender->ipc_quota_bytes ||
        usage.pending_bytes + charged > PROFILE_IPC_PENDING_BYTES_GLOBAL || slot == NO_MESSAGE) {
        return -KERNEL_ERROR_LIMIT_EXCEEDED;
    }
    if (frame_pool_allocate(physical_memory_pool(), order, FRAME_FOR_PROCESS, &frame) != FRAME_OK) {
        return -KERNEL_ERROR_OUT_OF_MEMORY;
    }
    memcpy((void *)(uintptr_t)frame, bytes, length);
    message = &messages[slot];
    free_message = message->next;
    *message = (struct queued_message){
        .next = NO_MESSAGE,
        .length = length,
        .order = order,
        .sender = sender->index,
        .sender_handle = sender->handle,
        .frame = frame,
        .transferred = transferred,
        .reply = reply,
    };
    if (endpoint->tail == NO_MESSAGE) {
        endpoint->head = slot;
    } else {
        messages[endpoint->tail].next = slot;
    }
    endpoint->tail = slot;
    endpoint->count++;
    sender->ipc_pending_bytes += charged;
    usage.pending_bytes += charged;
    usage.messages++;
    return KERNEL_OK;
}

bool endpoint_peek(uint32_t index, struct ipc_delivery *delivery)
{
    const struct queued_message *message;

    if (endpoints[index].head == NO_MESSAGE) {
        return false;
    }
    message = &messages[endpoints[index].head];
    *delivery = (struct ipc_delivery){
        .bytes = (const uint8_t *)(uintptr_t)message->frame,
        .length = message->length,
        .sender = message->sender_handle,
        .transferred = message->transferred,
        .reply = message->reply,
    };
    return true;
}

void endpoint_dequeue(uint32_t index)
{
    struct endpoint *endpoint = &endpoints[index];

    if (endpoint->head == NO_MESSAGE) {
        return;
    }
    release_message(unlink_head(endpoint));
    wake_sender(index);
}

void endpoint_remove_reply(uint32_t index, uint64_t reply)
{
    struct endpoint *endpoint = &endpoints[index];
    uint32_t previous = NO_MESSAGE;

    for (uint32_t current = endpoint->head; current != NO_MESSAGE;
         previous = current, current = messages[current].next) {
        uint64_t transferred = messages[current].transferred;

        if (messages[current].reply != reply) {
            continue;
        }
        if (previous == NO_MESSAGE) {
            endpoint->head = messages[current].next;
        } else {
            messages[previous].next = messages[current].next;
        }
        if (endpoint->tail == current) {
            endpoint->tail = previous;
        }
        endpoint->count--;
        release_message(current);
        if (transferred != 0) {
            capability_close(kernel_capabilities(), endpoint->owner, transferred);
        }
        wake_sender(index);
        return;
    }
}

void endpoint_wake_receiver(uint32_t index)
{
    struct process *owner = process_at(endpoints[index].owner);

    if (owner != NULL && owner->state == PROCESS_BLOCKED && owner->wait.kind == WAIT_RECEIVE &&
        owner->wait.object == index) {
        wait_restart(owner);
    }
}

struct ipc_usage endpoint_usage(void)
{
    return usage;
}
