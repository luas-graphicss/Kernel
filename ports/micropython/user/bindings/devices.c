#include "py/obj.h"
#include "py/runtime.h"

#include "bindings/bindings.h"
#include "kernel/abi/devices.h"
#include "kernel/abi/syscalls.h"
#include "kernel/memory/endian.h"
#include "process_calls.h"

#define WORD_BYTES 4u
#define DOUBLE_WORD_BYTES 8u
#define SEGMENT_FIELDS 4u
#define WORD_MAX 0xffffffffll

static mp_obj_t field(const uint8_t *bytes, size_t offset, size_t width)
{
    return binding_unsigned(little_endian_read(bytes + offset, width));
}

static uint64_t word_argument(mp_obj_t value)
{
    mp_int_t word = mp_obj_get_int(value);

    if (word < 0 || word > WORD_MAX) {
        mp_raise_ValueError(MP_ERROR_TEXT("segment field does not fit in 32 bits"));
    }
    return (uint64_t)word;
}

static void encode_segment(uint8_t *segment, mp_obj_t described)
{
    mp_obj_t *fields;

    mp_obj_get_array_fixed_n(described, SEGMENT_FIELDS, &fields);
    little_endian_write(segment + DEVICE_SEGMENT_BUFFER, DOUBLE_WORD_BYTES,
                        (uint64_t)binding_argument(fields[0]));
    little_endian_write(segment + DEVICE_SEGMENT_OFFSET, WORD_BYTES, word_argument(fields[1]));
    little_endian_write(segment + DEVICE_SEGMENT_LENGTH, WORD_BYTES, word_argument(fields[2]));
    little_endian_write(segment + DEVICE_SEGMENT_FLAGS, WORD_BYTES,
                        mp_obj_is_true(fields[3]) ? DEVICE_SEGMENT_WRITABLE : 0);
}

static mp_obj_t process_device_list_binding(mp_obj_t system)
{
    uint8_t entries[DEVICE_SLOTS * DEVICE_ENTRY_BYTES];
    long count = process_call(binding_argument(system), (long)entries, sizeof(entries), 0, 0, 0,
                              SYSCALL_DEVICE_LIST);
    mp_obj_tuple_t *devices;

    if (count < 0) {
        return binding_signed(count);
    }
    devices = MP_OBJ_TO_PTR(mp_obj_new_tuple((size_t)count, NULL));
    for (size_t index = 0; index < (size_t)count; index++) {
        const uint8_t *entry = entries + index * DEVICE_ENTRY_BYTES;
        mp_obj_t items[] = {
            field(entry, DEVICE_ENTRY_SLOT, WORD_BYTES),
            field(entry, DEVICE_ENTRY_KIND, WORD_BYTES),
            field(entry, DEVICE_ENTRY_MODEL, WORD_BYTES),
            field(entry, DEVICE_ENTRY_STATE, WORD_BYTES),
        };

        devices->items[index] = mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
    }
    return MP_OBJ_FROM_PTR(devices);
}
MP_DEFINE_CONST_FUN_OBJ_1(process_device_list_obj, process_device_list_binding);

static mp_obj_t process_device_open_binding(mp_obj_t device, mp_obj_t features)
{
    uint8_t session[DEVICE_SESSION_BYTES];
    long status = process_call(binding_argument(device), binding_argument(features), (long)session,
                               0, 0, 0, SYSCALL_DEVICE_OPEN);

    if (status < 0) {
        return binding_signed(status);
    }
    mp_obj_t items[] = {
        field(session, DEVICE_SESSION_FEATURES, DOUBLE_WORD_BYTES),
        field(session, DEVICE_SESSION_GENERATION, DOUBLE_WORD_BYTES),
        field(session, DEVICE_SESSION_QUEUE_SIZE, WORD_BYTES),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_2(process_device_open_obj, process_device_open_binding);

static mp_obj_t process_device_config_binding(mp_obj_t device, mp_obj_t offset, mp_obj_t length)
{
    uint8_t bytes[DEVICE_CONFIG_BYTES];
    mp_int_t wanted = mp_obj_get_int(length);
    long status;

    if (wanted < 0 || wanted > (mp_int_t)DEVICE_CONFIG_BYTES) {
        mp_raise_ValueError(MP_ERROR_TEXT("range is outside the device configuration"));
    }
    status = process_call(binding_argument(device), binding_argument(offset), (long)bytes, wanted, 0,
                          0, SYSCALL_DEVICE_CONFIG);
    if (status < 0) {
        return binding_signed(status);
    }
    return mp_obj_new_bytes(bytes, (size_t)status);
}
MP_DEFINE_CONST_FUN_OBJ_3(process_device_config_obj, process_device_config_binding);

static mp_obj_t process_device_submit_binding(mp_obj_t device, mp_obj_t described)
{
    uint8_t request[DEVICE_REQUEST_BYTES] = {0};
    mp_obj_t *segments;
    size_t count;

    mp_obj_get_array(described, &count, &segments);
    if (count > DEVICE_SEGMENTS) {
        mp_raise_ValueError(MP_ERROR_TEXT("too many segments in a device request"));
    }
    little_endian_write(request + DEVICE_REQUEST_SEGMENT_COUNT, WORD_BYTES, count);
    for (size_t index = 0; index < count; index++) {
        encode_segment(request + DEVICE_REQUEST_SEGMENTS + index * DEVICE_SEGMENT_BYTES,
                       segments[index]);
    }
    return binding_signed(
        process_call(binding_argument(device), (long)request, 0, 0, 0, 0, SYSCALL_DEVICE_SUBMIT));
}
MP_DEFINE_CONST_FUN_OBJ_2(process_device_submit_obj, process_device_submit_binding);

static mp_obj_t process_device_wait_binding(mp_obj_t device, mp_obj_t deadline)
{
    uint8_t completion[DEVICE_COMPLETION_BYTES];
    long status = process_call(binding_argument(device), (long)completion,
                               binding_argument(deadline), 0, 0, 0, SYSCALL_DEVICE_WAIT);

    if (status < 0) {
        return binding_signed(status);
    }
    mp_obj_t items[] = {
        field(completion, DEVICE_COMPLETION_TOKEN, DOUBLE_WORD_BYTES),
        field(completion, DEVICE_COMPLETION_LENGTH, WORD_BYTES),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
MP_DEFINE_CONST_FUN_OBJ_2(process_device_wait_obj, process_device_wait_binding);

static mp_obj_t process_serial_write_binding(mp_obj_t device, mp_obj_t data)
{
    mp_buffer_info_t bytes;

    mp_get_buffer_raise(data, &bytes, MP_BUFFER_READ);
    return binding_signed(process_call(binding_argument(device), (long)bytes.buf, (long)bytes.len,
                                       0, 0, 0, SYSCALL_SERIAL_WRITE));
}
MP_DEFINE_CONST_FUN_OBJ_2(process_serial_write_obj, process_serial_write_binding);

static mp_obj_t process_serial_read_binding(mp_obj_t device, mp_obj_t capacity, mp_obj_t deadline)
{
    uint8_t bytes[SERIAL_TRANSFER_BYTES];
    mp_int_t wanted = mp_obj_get_int(capacity);
    long status;

    if (wanted < 0 || wanted > (mp_int_t)SERIAL_TRANSFER_BYTES) {
        mp_raise_ValueError(MP_ERROR_TEXT("serial read is larger than one transfer"));
    }
    status = process_call(binding_argument(device), (long)bytes, wanted,
                          binding_argument(deadline), 0, 0, SYSCALL_SERIAL_READ);
    if (status < 0) {
        return binding_signed(status);
    }
    return mp_obj_new_bytes(bytes, (size_t)status);
}
MP_DEFINE_CONST_FUN_OBJ_3(process_serial_read_obj, process_serial_read_binding);
