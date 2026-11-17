#include <stdlib.h>
#include <string.h>

#include "kernel/abi/errors.h"
#include "kernel/abi/ipc.h"
#include "kernel/abi/process.h"
#include "kernel/ipc/message.h"
#include "kernel/processes/spawn_request.h"
#include "targets.h"

#define UNWRITTEN 0xff

int64_t fuzz_ipc_message(const uint8_t *data, size_t length)
{
    struct ipc_header header;
    int64_t status = ipc_message_parse(data, length, &header);

    if (status == KERNEL_OK) {
        FUZZ_REQUIRE(header.payload_bytes <= IPC_MAX_PAYLOAD_BYTES);
        FUZZ_REQUIRE((uint64_t)header.payload_bytes + IPC_HEADER_BYTES == length);
    }
    return status;
}

int64_t fuzz_spawn_request(const uint8_t *data, size_t length)
{
    uint8_t *bytes = calloc(1, SPAWN_REQUEST_BYTES);
    struct spawn_request request;
    int64_t status;

    FUZZ_REQUIRE(bytes != NULL);
    memcpy(bytes, data, length < SPAWN_REQUEST_BYTES ? length : SPAWN_REQUEST_BYTES);
    memset(&request, UNWRITTEN, sizeof(request));
    status = spawn_request_parse(bytes, &request);
    free(bytes);
    if (status == KERNEL_OK) {
        FUZZ_REQUIRE(request.name_length <= PROCESS_NAME_BYTES);
        FUZZ_REQUIRE(request.name[request.name_length] == '\0');
        FUZZ_REQUIRE(program_name_is_valid(request.name, request.name_length));
        FUZZ_REQUIRE(request.argument_length <= PROCESS_ARGUMENT_BYTES);
        FUZZ_REQUIRE(request.grant_count <= PROCESS_GRANTS);
    }
    return status;
}
