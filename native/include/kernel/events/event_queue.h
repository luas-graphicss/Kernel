#ifndef KERNEL_EVENTS_EVENT_QUEUE_H
#define KERNEL_EVENTS_EVENT_QUEUE_H

#include <stdbool.h>
#include <stdint.h>

struct kernel_event {
    uint32_t kind;
    uint64_t subject;
};

struct event_queue {
    struct kernel_event *slots;
    uint32_t capacity;
    uint32_t head;
    uint32_t count;
    uint64_t dropped;
    bool overflowed;
};

void event_queue_init(struct event_queue *queue, struct kernel_event *slots, uint32_t capacity);
bool event_queue_push(struct event_queue *queue, struct kernel_event event);
bool event_queue_pop(struct event_queue *queue, struct kernel_event *event);
bool event_queue_take_overflow(struct event_queue *queue);

#endif
