from suites.ipc import (
    cancellation_case,
    correlation_case,
    deadline_case,
    deadlock_case,
    delivery_case,
    framing_case,
    ownership_case,
    peers_case,
    queue_case,
)
from suites.support.reporting import run_suite

CASES = (
    ("malformed-messages", framing_case.run),
    ("delivery-and-transfer", delivery_case.run),
    ("queue-limits", queue_case.run),
    ("peer-death", peers_case.run),
    ("cancellation", cancellation_case.run),
    ("deadlines", deadline_case.run),
    ("reply-correlation", correlation_case.run),
    ("endpoint-ownership", ownership_case.run),
    ("deadlock-refusal", deadlock_case.run),
)


def main() -> bool:
    return run_suite("ipc", CASES)
