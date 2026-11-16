#include "kernel/ipc/message.h"

#include "kernel/abi/errors.h"
#include "kernel/abi/ipc.h"
#include "kernel/memory/endian.h"

#define KNOWN_FLAGS (IPC_FLAG_REPLY | IPC_FLAG_ERROR)

static uint64_t field(const uint8_t *bytes, uint32_t offset, uint32_t width)
{
    return little_endian_read(bytes + offset, width);
}

int64_t ipc_message_parse(const uint8_t *bytes, uint64_t length, struct ipc_header *header)
{
    uint64_t flags;
    uint64_t payload_bytes;

    if (length < IPC_HEADER_BYTES) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    if (field(bytes, IPC_FIELD_VERSION, 2) != IPC_VERSION) {
        return -KERNEL_ERROR_UNSUPPORTED;
    }
    flags = field(bytes, IPC_FIELD_FLAGS, 2);
    if ((flags & ~(uint64_t)KNOWN_FLAGS) != 0 ||
        (flags & KNOWN_FLAGS) == IPC_FLAG_ERROR || field(bytes, IPC_FIELD_RESERVED, 4) != 0) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    payload_bytes = field(bytes, IPC_FIELD_PAYLOAD_BYTES, 4);
    if (payload_bytes > IPC_MAX_PAYLOAD_BYTES) {
        return -KERNEL_ERROR_MESSAGE_TOO_LARGE;
    }
    if (length != IPC_HEADER_BYTES + payload_bytes) {
        return -KERNEL_ERROR_INVALID_ARGUMENT;
    }
    *header = (struct ipc_header){
        .flags = (uint16_t)flags,
        .operation = (uint32_t)field(bytes, IPC_FIELD_OPERATION, 4),
        .payload_bytes = (uint32_t)payload_bytes,
        .correlation = field(bytes, IPC_FIELD_CORRELATION, 8),
    };
    return KERNEL_OK;
}
