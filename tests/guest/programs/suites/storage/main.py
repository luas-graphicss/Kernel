from suites.storage import capacity_case, durability_case, restart_case
from suites.support.platform import run_with_services

CASES = (
    ("durable-after-sync", durability_case.run),
    ("volume-full", capacity_case.run),
    ("block-service-restart", restart_case.run),
)


def main() -> bool:
    return run_with_services("storage", CASES)
