from suites.capabilities import (
    attenuation_case,
    authority_case,
    handles_case,
    mapping_case,
    quota_case,
    revocation_case,
)
from suites.support.reporting import run_suite

CASES = (
    ("stale-and-forged-handles", handles_case.run),
    ("attenuated-delegation", attenuation_case.run),
    ("revocation-with-descendants", revocation_case.run),
    ("capability-quota", quota_case.run),
    ("no-ambient-authority", authority_case.run),
    ("mappings-follow-capabilities", mapping_case.run),
)


def main() -> bool:
    return run_suite("capabilities", CASES)
