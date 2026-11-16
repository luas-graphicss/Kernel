from suites.supervision import order_case, readiness_case, restart_case
from suites.support.reporting import run_suite

CASES = (
    ("dependency-order", order_case.run),
    ("readiness-and-degraded-state", readiness_case.run),
    ("restart-with-a-pending-request", restart_case.run_restart),
    ("restart-budget", restart_case.run_budget),
    ("restart-window", restart_case.run_window),
)


def main() -> bool:
    return run_suite("supervision", CASES)
