import _probe

from kernel_client import capabilities, devices, processes
from kernel_protocol.devices.layout import SERIAL_TRANSFER_BYTES
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    MESSAGE_TOO_LARGE,
    TIMED_OUT,
    UNSUPPORTED,
)
from kernel_protocol.identity.rights import RIGHT_READ, RIGHT_WRITE
from kernel_protocol.syscalls.numbers import SERIAL_WRITE
from runtime_selftest.checks import Checks
from suites.devices.access import claim_entropy, claim_serial
from suites.support import raw
from suites.support.expectations import error_code
from suites.support.reporting import Context

GREETING = b"serial: written through the device capability\n"
SHORT_WAIT_NANOSECONDS = 2000000


def check_output(checks: Checks, serial: int) -> None:
    oversized = bytearray(SERIAL_TRANSFER_BYTES + 1)
    reader = capabilities.derive(serial, RIGHT_READ)
    checks.require(
        devices.serial_write(serial, GREETING) == len(GREETING),
        "the port accepts a line while the transmitter is free",
    )
    checks.require(devices.serial_write(serial, b"") == 0, "an empty write accepts nothing")
    checks.require(
        -raw.call(SERIAL_WRITE, serial, _probe.address(oversized), len(oversized))
        == MESSAGE_TOO_LARGE,
        "a write larger than one transfer is refused",
    )
    checks.require(
        error_code(devices.serial_write, reader, GREETING) == ACCESS_DENIED,
        "writing needs the write right over the port",
    )
    capabilities.close(reader)


def check_input(checks: Checks, serial: int) -> None:
    writer = capabilities.derive(serial, RIGHT_WRITE)
    soon = processes.clock() + SHORT_WAIT_NANOSECONDS
    checks.require(
        error_code(devices.serial_read, serial, 1, soon) == TIMED_OUT,
        "a read waits for input until its deadline",
    )
    checks.require(
        error_code(devices.serial_read, serial, 0) == INVALID_ARGUMENT,
        "a read asks for at least one byte",
    )
    checks.require(
        error_code(devices.serial_read, writer, 1, soon) == ACCESS_DENIED,
        "reading needs the read right over the port",
    )
    capabilities.close(writer)


def run(context: Context, checks: Checks) -> None:
    serial = claim_serial(context)
    entropy = claim_entropy(context)
    check_output(checks, serial)
    check_input(checks, serial)
    checks.require(
        error_code(devices.serial_write, entropy, GREETING) == UNSUPPORTED
        and error_code(devices.reset, serial) == UNSUPPORTED,
        "a device only answers the calls of its kind",
    )
    capabilities.close(entropy)
    capabilities.close(serial)
