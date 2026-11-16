from suites.device_reset import deadline_case, exit_case, failure_case, pinned_case
from suites.support.reporting import run_suite

CASES = (
    ("request-deadline-and-reset", deadline_case.run),
    ("memory-pinned-until-reset", pinned_case.run),
    ("exit-with-a-request-in-flight", exit_case.run),
    ("device-reported-failure", failure_case.run),
)


def main() -> bool:
    return run_suite("device-reset", CASES)
