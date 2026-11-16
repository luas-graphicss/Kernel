#ifndef KERNEL_IPC_MESSAGE_H
#define KERNEL_IPC_MESSAGE_H

#include <stdint.h>

struct ipc_header {
    uint16_t flags;
    uint32_t operation;
    uint32_t payload_bytes;
    uint64_t correlation;
};

int64_t ipc_message_parse(const uint8_t *bytes, uint64_t length, struct ipc_header *header);

#endif
