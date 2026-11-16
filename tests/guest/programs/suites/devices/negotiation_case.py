from kernel_client import capabilities, devices
from kernel_drivers.virtio_block.driver import FEATURE_FLUSH
from kernel_protocol.devices.layout import DEVICE_CONFIG_BYTES, DEVICE_QUEUE_SIZE
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    BAD_STATE,
    INVALID_ARGUMENT,
    UNSUPPORTED,
)
from kernel_protocol.identity.rights import RIGHT_READ, RIGHT_WRITE
from runtime_selftest.checks import Checks
from suites.devices.access import claim_block, claim_serial
from suites.support.expectations import error_code
from suites.support.reporting import Context

TRANSPORT_FEATURE = 1 << 28
NEVER_OFFERED_FEATURE = 1 << 20
WANTED_FEATURES = FEATURE_FLUSH | NEVER_OFFERED_FEATURE
CAPACITY_BYTES = 8


def check_refusals(context: Context, checks: Checks, device: int) -> None:
    serial = claim_serial(context)
    operator = capabilities.derive(device, RIGHT_READ | RIGHT_WRITE)
    checks.require(
        error_code(devices.open_session, device, TRANSPORT_FEATURE) == INVALID_ARGUMENT,
        "a driver cannot ask for transport features",
    )
    checks.require(
        error_code(devices.open_session, operator, 0) == ACCESS_DENIED,
        "opening a device needs the admin right over it",
    )
    checks.require(
        error_code(devices.open_session, serial, 0) == UNSUPPORTED,
        "the serial port has no transport to negotiate",
    )
    checks.require(
        error_code(devices.read_config, device, 0, CAPACITY_BYTES) == BAD_STATE,
        "configuration is read only through an open session",
    )
    capabilities.close(operator)
    capabilities.close(serial)


def check_session(checks: Checks, device: int) -> None:
    session = devices.open_session(device, WANTED_FEATURES)
    checks.require(
        session.features == FEATURE_FLUSH,
        "the accepted features are the wanted ones the device offers",
    )
    checks.require(session.queue_size == DEVICE_QUEUE_SIZE, "the queue has the transport size")
    checks.require(
        error_code(devices.open_session, device, 0) == BAD_STATE,
        "an open device is not opened again",
    )
    checks.require(
        len(devices.read_config(device, 0, CAPACITY_BYTES)) == CAPACITY_BYTES,
        "the session reads the device configuration",
    )
    checks.require(
        error_code(devices.read_config, device, DEVICE_CONFIG_BYTES - 4, CAPACITY_BYTES)
        == INVALID_ARGUMENT
        and error_code(devices.read_config, device, 0, 0) == INVALID_ARGUMENT,
        "configuration reads stay inside the configuration space",
    )
    devices.reset(device)
    reopened = devices.open_session(device, 0)
    checks.require(
        reopened.generation > session.generation and reopened.features == 0,
        "a reset ends the session and the next one negotiates again",
    )
    devices.reset(device)


def run(context: Context, checks: Checks) -> None:
    device = claim_block(context)
    check_refusals(context, checks, device)
    check_session(checks, device)
    capabilities.close(device)
