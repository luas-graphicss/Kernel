from kernel_client import capabilities, devices, memory, system
from kernel_protocol.processes.status import (
    COUNTER_DEVICE_REQUESTS,
    COUNTER_FRAMES_FREE,
    COUNTER_PINNED_BUFFERS,
)
from runtime_selftest.checks import Checks
from suites.device_reset.requests import submit_read
from suites.devices.access import claim_block
from suites.support.layout import PAGE_BYTES
from suites.support.reporting import Context


def map_once() -> None:
    buffer = memory.create_buffer(PAGE_BYTES)
    memory.Mapping(buffer, True).unmap()
    capabilities.close(buffer)


def run(context: Context, checks: Checks) -> None:
    device = claim_block(context)
    devices.open_session(device, 0)
    map_once()
    before = system.counters(context.system)
    buffer = memory.create_buffer(PAGE_BYTES)
    submit_read(device, buffer)
    capabilities.close(buffer)
    during = system.counters(context.system)
    checks.require(
        during[COUNTER_DEVICE_REQUESTS] == 1 and during[COUNTER_PINNED_BUFFERS] == 1,
        "a request in flight keeps its buffer pinned",
    )
    checks.require(
        during[COUNTER_FRAMES_FREE] < before[COUNTER_FRAMES_FREE],
        "memory the device may still write is not given back when its owner closes it",
    )
    devices.reset(device)
    after = system.counters(context.system)
    checks.require(
        after[COUNTER_DEVICE_REQUESTS] == 0 and after[COUNTER_PINNED_BUFFERS] == 0,
        "the reset leaves nothing in flight",
    )
    checks.require(
        after[COUNTER_FRAMES_FREE] == before[COUNTER_FRAMES_FREE],
        "the memory returns only after the device was quiesced",
    )
    capabilities.close(device)
