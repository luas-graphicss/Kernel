from suites.processes import (
    authority_case,
    capacity_case,
    context_case,
    lifecycle_case,
    preemption_case,
    teardown_case,
)
from suites.support.reporting import run_suite

CASES = (
    ("exit-status-and-finalization", lifecycle_case.run),
    ("spawn-authority-and-validation", authority_case.run),
    ("preemption-of-a-loop", preemption_case.run),
    ("register-preservation", context_case.run),
    ("process-capacity", capacity_case.run),
    ("teardown-releases-resources", teardown_case.run),
)


def main() -> bool:
    return run_suite("processes", CASES)
