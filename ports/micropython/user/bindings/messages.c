#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"
#include "kernel/abi/ipc.h"
#include "kernel/abi/syscalls.h"
#include "kernel/memory/endian.h"
#include "process_calls.h"

#define SEND_ARGUMENTS 4
#define REQUEST_ARGUMENTS 5
#define DOUBLE_WORD_BYTES 8u

static uint64_t metadata_field(const uint8_t *metadata, size_t offset)
{
    return little_endian_read(metadata + offset, DOUBLE_WORD_BYTES);
}

static mp_obj_t process_send_binding(size_t count, const mp_obj_t *arguments)
{
    mp_buffer_info_t message;

    (void)count;
    mp_get_buffer_raise(arguments[1], &message, MP_BUFFER_READ);
    return binding_signed(process_call(binding_argument(arguments[0]), (long)message.buf,
                                       (long)message.len, binding_argument(arguments[2]),
                                       binding_argument(arguments[3]), 0, SYSCALL_IPC_SEND));
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(process_send_obj, SEND_ARGUMENTS, SEND_ARGUMENTS,
                                    process_send_binding);

static mp_obj_t process_receive_binding(mp_obj_t endpoint, mp_obj_t buffer, mp_obj_t deadline)
{
    uint8_t metadata[IPC_METADATA_BYTES] = {0};
    mp_buffer_info_t storage;
    long status;

    mp_get_buffer_raise(buffer, &storage, MP_BUFFER_WRITE);
    status = process_call(binding_argument(endpoint), (long)storage.buf, (long)storage.len,
                          (long)metadata, binding_argument(deadline), 0, SYSCALL_IPC_RECEIVE);
    mp_obj_t items[] = {
        binding_signed(status),
        binding_unsigned(metadata_field(metadata, IPC_METADATA_SENDER)),
        binding_unsigned(metadata_field(metadata, IPC_METADATA_TRANSFERRED)),
        binding_unsigned(metadata_field(metadata, IPC_METADATA_REPLY)),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_3(process_receive_obj, process_receive_binding);

static mp_obj_t process_request_binding(size_t count, const mp_obj_t *arguments)
{
    uint8_t control[IPC_CALL_CONTROL_BYTES] = {0};
    mp_buffer_info_t message;
    mp_buffer_info_t response;
    long status;

    (void)count;
    mp_get_buffer_raise(arguments[1], &message, MP_BUFFER_READ);
    mp_get_buffer_raise(arguments[2], &response, MP_BUFFER_WRITE);
    little_endian_write(control + IPC_CALL_TRANSFER, DOUBLE_WORD_BYTES,
                        (uint64_t)binding_argument(arguments[3]));
    little_endian_write(control + IPC_CALL_DEADLINE, DOUBLE_WORD_BYTES,
                        (uint64_t)binding_argument(arguments[4]));
    status = process_call(binding_argument(arguments[0]), (long)message.buf, (long)message.len,
                          (long)response.buf, (long)response.len, (long)control, SYSCALL_IPC_CALL);
    mp_obj_t items[] = {
        binding_signed(status),
        binding_unsigned(metadata_field(control, IPC_CALL_RECEIVED)),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(process_request_obj, REQUEST_ARGUMENTS, REQUEST_ARGUMENTS,
                                    process_request_binding);

static mp_obj_t process_reply_binding(mp_obj_t reply, mp_obj_t message, mp_obj_t transfer)
{
    mp_buffer_info_t bytes;

    mp_get_buffer_raise(message, &bytes, MP_BUFFER_READ);
    return binding_signed(process_call(binding_argument(reply), (long)bytes.buf, (long)bytes.len,
                                       binding_argument(transfer), 0, 0, SYSCALL_IPC_REPLY));
}
MP_DEFINE_CONST_FUN_OBJ_3(process_reply_obj, process_reply_binding);
