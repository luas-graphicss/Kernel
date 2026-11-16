#include "kernel/events/event_queue.h"

void event_queue_init(struct event_queue *queue, struct kernel_event *slots, uint32_t capacity)
{
    *queue = (struct event_queue){.slots = slots, .capacity = capacity};
}

bool event_queue_push(struct event_queue *queue, struct kernel_event event)
{
    if (queue->count == queue->capacity) {
        queue->dropped++;
        queue->overflowed = true;
        return false;
    }
    queue->slots[(queue->head + queue->count) % queue->capacity] = event;
    queue->count++;
    return true;
}

bool event_queue_pop(struct event_queue *queue, struct kernel_event *event)
{
    if (queue->count == 0) {
        return false;
    }
    *event = queue->slots[queue->head];
    queue->head = (queue->head + 1u) % queue->capacity;
    queue->count--;
    return true;
}

bool event_queue_take_overflow(struct event_queue *queue)
{
    bool overflowed = queue->overflowed;

    queue->overflowed = false;
    return overflowed;
}
