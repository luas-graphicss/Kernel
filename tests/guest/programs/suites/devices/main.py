from suites.devices import (
    block_case,
    claims_case,
    entropy_case,
    exit_case,
    negotiation_case,
    serial_case,
    validation_case,
)
from suites.support.reporting import run_suite

CASES = (
    ("discovery-and-claims", claims_case.run),
    ("feature-negotiation", negotiation_case.run),
    ("descriptor-validation", validation_case.run),
    ("block-requests", block_case.run),
    ("entropy-source", entropy_case.run),
    ("serial-port", serial_case.run),
    ("driver-exit-with-requests", exit_case.run),
)


def main() -> bool:
    return run_suite("devices", CASES)
