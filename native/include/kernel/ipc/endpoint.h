#ifndef KERNEL_IPC_ENDPOINT_H
#define KERNEL_IPC_ENDPOINT_H

#include <stdbool.h>
#include <stdint.h>

#include "kernel/processes/process.h"

struct ipc_delivery {
    const uint8_t *bytes;
    uint32_t length;
    uint64_t sender;
    uint64_t transferred;
    uint64_t reply;
};

struct ipc_usage {
    uint64_t endpoints;
    uint64_t messages;
    uint64_t pending_bytes;
};

void endpoint_table_init(void);
int64_t endpoint_allocate(uint32_t owner);
void endpoint_close(uint32_t endpoint);
void endpoint_dispose(uint32_t endpoint);
bool endpoint_is_open(uint32_t endpoint);
bool endpoint_is_full(uint32_t endpoint);
uint32_t endpoint_owner(uint32_t endpoint);
int64_t endpoint_enqueue(uint32_t endpoint, struct process *sender, const uint8_t *bytes,
                         uint32_t length, uint64_t transferred, uint64_t reply);
bool endpoint_peek(uint32_t endpoint, struct ipc_delivery *delivery);
void endpoint_dequeue(uint32_t endpoint);
void endpoint_remove_reply(uint32_t endpoint, uint64_t reply);
void endpoint_wake_receiver(uint32_t endpoint);
struct ipc_usage endpoint_usage(void);

#endif
