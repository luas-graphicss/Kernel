from suites.memory import (
    clearing_case,
    forbidden_access_case,
    isolation_case,
    pointers_case,
    quota_case,
    remapping_case,
    sharing_case,
)
from suites.support.reporting import run_suite

CASES = (
    ("forbidden-access", forbidden_access_case.run),
    ("private-address-spaces", isolation_case.run),
    ("system-call-pointers", pointers_case.run),
    ("shared-buffers", sharing_case.run),
    ("mapping-removed-while-blocked", remapping_case.run),
    ("memory-cleared-between-processes", clearing_case.run),
    ("quotas-and-reserve", quota_case.run),
)


def main() -> bool:
    return run_suite("memory", CASES)
