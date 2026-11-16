import pytest

from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.services.control import (
    APPLICATION_EXITED,
    APPLICATION_RUNNING,
    MAX_NAME_BYTES,
    SERVICE_DEGRADED,
    SERVICE_READY,
    SERVICE_STATE_NAMES,
    SYSTEM_DEGRADED,
    SYSTEM_STATE_NAMES,
    WAIT_FOREVER,
    ApplicationStatus,
    ServiceStatus,
    decode_action,
    decode_applications,
    decode_counters,
    decode_identity,
    decode_name,
    decode_outcome,
    decode_status,
    decode_wait,
    encode_action,
    encode_applications,
    encode_counters,
    encode_identity,
    encode_name,
    encode_outcome,
    encode_status,
    encode_wait,
)


def refused(operation, *arguments) -> int:
    with pytest.raises(KernelError) as raised:
        operation(*arguments)
    return raised.value.code


def test_the_system_status_lists_every_service_with_its_restart_budget() -> None:
    services = [
        ServiceStatus("console", SERVICE_READY, 0, 2, 1),
        ServiceStatus("network", SERVICE_DEGRADED, 3, 3, 0),
    ]

    state, decoded = decode_status(encode_status(SYSTEM_DEGRADED, services))

    assert state == SYSTEM_DEGRADED
    assert [
        (service.name, service.state, service.failures, service.restarts, service.starts)
        for service in decoded
    ] == [("console", SERVICE_READY, 0, 2, 1), ("network", SERVICE_DEGRADED, 3, 3, 0)]
    assert SYSTEM_STATE_NAMES[state] == "degraded"
    assert SERVICE_STATE_NAMES[SERVICE_DEGRADED] == "degraded"


def test_a_truncated_or_padded_status_is_refused() -> None:
    encoded = encode_status(SYSTEM_DEGRADED, [ServiceStatus("console", SERVICE_READY, 0, 2, 1)])

    assert refused(decode_status, b"") == INVALID_ARGUMENT
    assert refused(decode_status, encoded[:-1]) == INVALID_ARGUMENT
    assert refused(decode_status, encoded + b"\x00") == INVALID_ARGUMENT
    assert refused(decode_status, encoded[:4]) == INVALID_ARGUMENT


def test_applications_are_listed_with_their_command_and_outcome() -> None:
    applications = [
        ApplicationStatus(1, APPLICATION_EXITED, 1, 0, "boot/apps/counter.py one two"),
        ApplicationStatus(7, APPLICATION_RUNNING, 0, 0, "boot/apps/spin.py"),
    ]

    decoded = decode_applications(encode_applications(applications))

    assert [
        (found.identity, found.state, found.reason, found.value, found.command) for found in decoded
    ] == [
        (1, APPLICATION_EXITED, 1, 0, "boot/apps/counter.py one two"),
        (7, APPLICATION_RUNNING, 0, 0, "boot/apps/spin.py"),
    ]
    assert decode_applications(b"") == []
    assert refused(decode_applications, encode_applications(applications)[:-1]) == INVALID_ARGUMENT
    assert refused(decode_applications, b"\x00" * 5) == INVALID_ARGUMENT


def test_requests_carry_fixed_layouts_and_refuse_any_other_size() -> None:
    assert decode_identity(encode_identity(0xFFFFFFF)) == 0xFFFFFFF
    assert decode_wait(encode_wait(9, WAIT_FOREVER)) == (9, WAIT_FOREVER)
    assert decode_outcome(encode_outcome(2, 0xFFFFFFFF)) == (2, 0xFFFFFFFF)
    assert decode_action(encode_action(1)) == 1
    assert refused(decode_identity, b"\x00" * 3) == INVALID_ARGUMENT
    assert refused(decode_wait, b"\x00" * 11) == INVALID_ARGUMENT
    assert refused(decode_outcome, b"\x00" * 6) == INVALID_ARGUMENT
    assert refused(decode_action, b"") == INVALID_ARGUMENT
    assert refused(decode_action, b"\x00\x00") == INVALID_ARGUMENT


def test_service_names_are_short_and_never_empty() -> None:
    assert decode_name(encode_name("storage")) == "storage"
    assert refused(encode_name, "") == INVALID_ARGUMENT
    assert refused(encode_name, "x" * (MAX_NAME_BYTES + 1)) == INVALID_ARGUMENT
    assert refused(decode_name, b"") == INVALID_ARGUMENT
    assert refused(decode_name, b"x" * (MAX_NAME_BYTES + 1)) == INVALID_ARGUMENT


def test_counters_are_whole_words() -> None:
    counters = (62944, 59677, 512, 8, 0, 1 << 40)

    assert decode_counters(encode_counters(counters)) == list(counters)
    assert refused(decode_counters, encode_counters(counters)[:-1]) == INVALID_ARGUMENT
