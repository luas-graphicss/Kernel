from kernel_client import capabilities, devices, ipc
from kernel_protocol.errors.codes import BAD_STATE, OK
from kernel_protocol.identity.rights import RIGHT_SEND
from runtime_selftest.checks import Checks
from suites.device_reset.holder import OPERATION_SUBMITTED
from suites.devices.access import DRIVER_RIGHTS, claim_block, nothing_in_flight
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, KILLED, error_code
from suites.support.reporting import Context

HOLDER = "suites.device_reset.holder"


def run(context: Context, checks: Checks) -> None:
    device = claim_block(context)
    outcome = children.run(context.system, HOLDER, b"leave", grants=((device, DRIVER_RIGHTS),))
    checks.require(
        outcome == EXITED_CLEANLY, "a driver exits while the device still holds its request"
    )
    checks.require(
        nothing_in_flight(context), "the exit resets the device and unpins what the request used"
    )
    announcements = ipc.create_endpoint()
    grants = ((device, DRIVER_RIGHTS), (announcements, RIGHT_SEND))
    holder = children.start(context.system, HOLDER, b"linger", grants=grants)
    checks.require(
        ipc.receive(announcements).message.operation == OPERATION_SUBMITTED,
        "the driver announces the request it is waiting for",
    )
    checks.require(
        error_code(devices.open_session, device, 0) == BAD_STATE,
        "a device held by a live driver is not opened by another process",
    )
    checks.require(
        children.stop(holder) == KILLED, "the driver is killed while it waits for the device"
    )
    checks.require(nothing_in_flight(context), "the kill leaves nothing in flight")
    checks.require(
        error_code(devices.open_session, device, 0) == OK, "the next driver opens the device"
    )
    devices.reset(device)
    capabilities.close(announcements)
    capabilities.close(device)
