import _probe

from kernel_client import capabilities, devices, ipc, memory
from kernel_protocol.devices.layout import (
    DEVICE_REQUEST_BYTES,
    DEVICE_REQUESTS,
    DEVICE_SEGMENT_WRITABLE,
    DEVICE_SEGMENTS,
)
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    BAD_ADDRESS,
    BAD_STATE,
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    LIMIT_EXCEEDED,
)
from kernel_protocol.identity.rights import RIGHT_READ, RIGHT_WRITE
from kernel_protocol.syscalls.numbers import DEVICE_SUBMIT
from runtime_selftest.checks import Checks
from suites.devices.access import claim_entropy, nothing_in_flight
from suites.support import raw
from suites.support.expectations import error_code
from suites.support.layout import NULL_PAGE, PAGE_BYTES
from suites.support.reporting import Context

NEVER_ISSUED_HANDLE = 0x7F000001
SAMPLE_BYTES = 16
UNKNOWN_FLAG = 0x2
REQUEST_QUEUE = 0
UNKNOWN_QUEUE = 1
WORD_BYTES = 4
BYTE_ORDER = "little"


def refused(device: int, *segments: tuple[int, int, int, bool]) -> int:
    return error_code(devices.submit, device, segments)


def word(value: int) -> bytes:
    return value.to_bytes(WORD_BYTES, BYTE_ORDER)


def encoded_request(
    buffer: int,
    count: int = 1,
    flags: int = DEVICE_SEGMENT_WRITABLE,
    reserved: int = 0,
    queue: int = REQUEST_QUEUE,
) -> bytearray:
    segment = raw.word(buffer) + word(0) + word(SAMPLE_BYTES) + word(flags) + word(reserved)
    request = word(queue) + word(count) + segment
    return bytearray(request + bytes(DEVICE_REQUEST_BYTES - len(request)))


def raw_refusal(device: int, request: bytearray) -> int:
    return -raw.call(DEVICE_SUBMIT, device, _probe.address(request))


def check_ranges(checks: Checks, device: int, buffer: int) -> None:
    checks.require(refused(device) == INVALID_ARGUMENT, "a request names at least one segment")
    checks.require(
        refused(device, (buffer, PAGE_BYTES - 8, SAMPLE_BYTES, True)) == INVALID_ARGUMENT,
        "a segment cannot cross the end of its buffer",
    )
    checks.require(
        refused(device, (buffer, PAGE_BYTES, 1, True)) == INVALID_ARGUMENT,
        "a segment cannot start past its buffer",
    )
    checks.require(
        refused(device, (buffer, 0xFFFFFFFF, 0xFFFFFFFF, True)) == INVALID_ARGUMENT,
        "an offset and a length that overflow together are refused",
    )
    checks.require(
        refused(device, (buffer, 0, 0, True)) == INVALID_ARGUMENT, "an empty segment is refused"
    )
    checks.require(
        refused(device, (buffer, 0, SAMPLE_BYTES, True), (buffer, 32, SAMPLE_BYTES, False))
        == INVALID_ARGUMENT,
        "the device reads every segment before it writes one",
    )


def check_authority(checks: Checks, device: int, buffer: int) -> None:
    reader = capabilities.derive(buffer, RIGHT_READ)
    writer = capabilities.derive(buffer, RIGHT_WRITE)
    endpoint = ipc.create_endpoint()
    checks.require(
        refused(device, (reader, 0, SAMPLE_BYTES, True)) == ACCESS_DENIED,
        "the device does not write into memory granted for reading",
    )
    checks.require(
        refused(device, (writer, 0, SAMPLE_BYTES, False)) == ACCESS_DENIED,
        "the device does not read memory granted only for writing",
    )
    checks.require(
        refused(device, (endpoint, 0, SAMPLE_BYTES, True)) == INVALID_HANDLE
        and refused(device, (NEVER_ISSUED_HANDLE, 0, SAMPLE_BYTES, True)) == INVALID_HANDLE,
        "only a buffer capability of the caller names memory",
    )
    for handle in (reader, writer, endpoint):
        capabilities.close(handle)


def check_request_format(checks: Checks, device: int, buffer: int) -> None:
    checks.require(
        raw_refusal(device, encoded_request(buffer, count=DEVICE_SEGMENTS + 1)) == INVALID_ARGUMENT,
        "a request cannot name more segments than a chain holds",
    )
    checks.require(
        raw_refusal(device, encoded_request(buffer, reserved=1)) == INVALID_ARGUMENT
        and raw_refusal(device, encoded_request(buffer, flags=UNKNOWN_FLAG)) == INVALID_ARGUMENT
        and raw_refusal(device, encoded_request(buffer, queue=UNKNOWN_QUEUE)) == INVALID_ARGUMENT,
        "reserved fields, unknown flags and unknown queues are refused",
    )
    checks.require(
        -raw.call(DEVICE_SUBMIT, device, NULL_PAGE) == BAD_ADDRESS,
        "a request the caller cannot read is refused",
    )


def check_queue_limit(checks: Checks, device: int, buffer: int) -> None:
    segment = (buffer, 0, SAMPLE_BYTES, True)
    tokens = [devices.submit(device, (segment,)) for _request in range(DEVICE_REQUESTS)]
    checks.require(
        refused(device, segment) == LIMIT_EXCEEDED,
        "requests in flight and uncollected completions are bounded together",
    )
    collected = [devices.wait(device)[0] for _request in range(DEVICE_REQUESTS)]
    checks.require(
        sorted(collected) == sorted(tokens), "every request completes once with its own token"
    )
    checks.require(
        devices.submit(device, (segment,)) not in tokens, "a token is never issued twice"
    )
    devices.wait(device)


def run(context: Context, checks: Checks) -> None:
    device = claim_entropy(context)
    buffer = memory.create_buffer(PAGE_BYTES)
    checks.require(
        refused(device, (buffer, 0, SAMPLE_BYTES, True)) == BAD_STATE,
        "only the process that opened the device submits to it",
    )
    devices.open_session(device, 0)
    check_ranges(checks, device, buffer)
    check_authority(checks, device, buffer)
    check_request_format(checks, device, buffer)
    checks.require(nothing_in_flight(context), "a refused request pins no memory")
    check_queue_limit(checks, device, buffer)
    devices.reset(device)
    checks.require(nothing_in_flight(context), "a reset leaves nothing in flight")
    capabilities.close(buffer)
    capabilities.close(device)
