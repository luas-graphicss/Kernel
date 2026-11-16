from suites.services import authority_case, block_case, console_case, entropy_case
from suites.support.platform import run_with_services

CASES = (
    ("console-service", console_case.run),
    ("entropy-service", entropy_case.run),
    ("block-service", block_case.run),
    ("service-authority", authority_case.run),
)


def main() -> bool:
    return run_with_services("services", CASES)
