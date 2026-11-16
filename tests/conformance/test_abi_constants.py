from pathlib import Path
from types import ModuleType

from kernel_core.scheduling import selection
from kernel_protocol.errors import codes
from kernel_protocol.identity import rights
from kernel_protocol.processes import status
from kernel_protocol.syscalls import numbers
from kernel_protocol.wire import message, spawn
from kernel_tool.images import user_image
from kernel_tool.profiles.loader import DEFAULT_PROFILE, load_profile
from native_abi import definitions

REPOSITORY = Path(__file__).resolve().parents[2]
ERROR_PREFIX = "KERNEL_ERROR_"
SYSCALL_PREFIX = "SYSCALL_"
COUNTER_PREFIX = "COUNTER_"
NATIVE_PROCESS_NAMES = {
    "PRIORITY_LEVELS": "PROCESS_PRIORITY_LEVELS",
    "NAME_BYTES": "PROCESS_NAME_BYTES",
    "ARGUMENT_BYTES": "PROCESS_ARGUMENT_BYTES",
    "GRANTS": "PROCESS_GRANTS",
}
MESSAGE_FIELDS = {
    "IPC_VERSION": message.VERSION,
    "IPC_HEADER_BYTES": message.HEADER_BYTES,
    "IPC_MAX_PAYLOAD_BYTES": message.MAX_PAYLOAD_BYTES,
    "IPC_FLAG_REPLY": message.FLAG_REPLY,
    "IPC_FLAG_ERROR": message.FLAG_ERROR,
}


def integers(module: ModuleType) -> dict[str, int]:
    return {
        name: value
        for name, value in vars(module).items()
        if name.isupper() and isinstance(value, int)
    }


def test_error_codes_match_the_native_header() -> None:
    native = definitions("errors.h")
    errors = {
        name.removeprefix(ERROR_PREFIX): code
        for name, code in native.items()
        if name.startswith(ERROR_PREFIX)
    }

    assert native["KERNEL_OK"] == codes.OK
    assert errors == {name: code for code, name in enumerate(codes.NAMES) if code != codes.OK}
    for name, code in errors.items():
        assert getattr(codes, name) == code


def test_system_call_numbers_match_the_native_header() -> None:
    native = definitions("syscalls.h")

    assert {name.removeprefix(SYSCALL_PREFIX): value for name, value in native.items()} == integers(
        numbers
    )
    assert sorted(
        value for name, value in integers(numbers).items() if value < numbers.COUNT
    ) == list(range(numbers.COUNT))


def test_rights_and_object_kinds_match_the_native_header() -> None:
    assert definitions("rights.h") == integers(rights)


def test_process_limits_wait_reasons_and_counters_match_the_native_header() -> None:
    native = definitions("process.h")
    counters = {name for name in native if name.startswith(COUNTER_PREFIX)}

    for name, value in integers(status).items():
        assert native[NATIVE_PROCESS_NAMES.get(name, name)] == value, name
    assert counters == {name for name in integers(status) if name.startswith(COUNTER_PREFIX)}
    assert len(counters) == status.COUNTERS


def test_spawn_request_size_matches_the_native_layout() -> None:
    native = definitions("process.h")

    assert native["SPAWN_REQUEST_VERSION"] == spawn.REQUEST_VERSION
    assert native["SPAWN_REQUEST_BYTES"] == spawn.REQUEST_BYTES
    assert native["SPAWN_FIELD_ARGUMENT"] + native["PROCESS_ARGUMENT_BYTES"] == spawn.REQUEST_BYTES
    assert (
        native["SPAWN_FIELD_GRANTS"] + native["SPAWN_GRANT_BYTES"] * status.GRANTS
        == (native["SPAWN_FIELD_NAME"])
    )


def test_message_header_matches_the_native_header() -> None:
    native = definitions("ipc.h")

    for name, value in MESSAGE_FIELDS.items():
        assert native[name] == value, name
    assert native["IPC_FIELD_CORRELATION"] + 8 == message.HEADER_BYTES


def test_user_image_header_matches_the_native_header() -> None:
    native = definitions("user_image.h")

    assert native["USER_IMAGE_MAGIC"] == int.from_bytes(user_image.MAGIC, "little")
    assert native["USER_IMAGE_VERSION"] == user_image.VERSION
    assert native["USER_IMAGE_HEADER_BYTES"] == user_image.HEADER.size
    assert native["USER_IMAGE_GUARD_BYTES"] == user_image.GUARD_BYTES
    assert native["USER_IMAGE_FIELD_STACK_BYTES"] + 8 == user_image.HEADER.size


def test_policy_and_reference_profile_agree_with_the_native_limits() -> None:
    limits = load_profile(REPOSITORY, DEFAULT_PROFILE).limits

    assert selection.PRIORITY_LEVELS == status.PRIORITY_LEVELS
    assert limits.delegation_depth == rights.CAPABILITY_MAX_DEPTH
    assert limits.ipc_inline_payload_bytes == message.MAX_PAYLOAD_BYTES
    assert limits.endpoint_messages == definitions("ipc.h")["IPC_ENDPOINT_MESSAGES"]
