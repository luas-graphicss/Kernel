from suites.scheduling import (
    chain_case,
    clock_case,
    donation_case,
    priority_case,
    race_case,
    sharing_case,
    yielding_case,
)
from suites.support.reporting import run_suite

CASES = (
    ("round-robin-among-equals", sharing_case.run),
    ("priority-without-starvation", priority_case.run),
    ("priority-donation", donation_case.run),
    ("wait-chain-limit", chain_case.run),
    ("deadline-racing-a-reply", race_case.run),
    ("clock-limits", clock_case.run),
    ("yield-to-an-equal", yielding_case.run),
)


def main() -> bool:
    return run_suite("scheduling", CASES)
