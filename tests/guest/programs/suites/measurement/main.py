from suites.measurement import release_case, round_trip_case
from suites.support.reporting import run_suite


def main() -> bool:
    return run_suite(
        "measurement",
        (
            ("ipc-round-trip", round_trip_case.run),
            ("release-after-exit", release_case.run),
        ),
    )
