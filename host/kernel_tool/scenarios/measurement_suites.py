from dataclasses import replace

from kernel_tool.scenarios.guest_program import INIT_OPTION, case_lines, tests_image_scenario
from kernel_tool.scenarios.guest_suites import CYCLES
from kernel_tool.scenarios.model import BootEntry, Deadline
from kernel_tool.scenarios.release_suites import test_application
from kernel_tool.scenarios.shell import MANAGER_PROGRAM, completed, said, system_scenario
from kernel_tool.scenarios.system_suites import (
    ACCEPTED,
    CLEAN_NETWORK,
    RUNNING,
    STOPPED_CLEANLY,
    exited,
)

MEASUREMENT = "measurement"
MEASUREMENT_PROGRAM = "suites.measurement.main"
MEASUREMENT_CONFIGURATION = "tests/guest/configurations/measurement.conf"
COLLECTOR_TRACE = " trace=collector"
MEMORY_REPORT = said(r"mem: frames-usable=\d+ frames-free=\d+ frames-reserved=\d+ bytes-free=\d+")
MEASURED_CASES = ("ipc-round-trip", "release-after-exit")
CPU_BOUND_TASKS = 4
IO_BOUND_TASKS = 2
MEMORY_HOLDERS = 4
SETTLE_SECONDS = 2
LATENCY_APPLICATION = CPU_BOUND_TASKS + IO_BOUND_TASKS + 1
LOADED_APPLICATIONS = tuple(range(1, LATENCY_APPLICATION))
HOLDER_APPLICATIONS = tuple(
    range(LATENCY_APPLICATION + 1, LATENCY_APPLICATION + 1 + MEMORY_HOLDERS)
)


def measured(name: str) -> str:
    return rf"measure: name={name} samples=\d+ p50-us=\d+ p99-us=\d+ max-us=\d+$"


def stopped(application: int) -> tuple[str, str]:
    return (f"kill {application}", f"wait {application} 10")


def reported_stop(application: int) -> tuple[str, str]:
    return (
        said(rf"kill: application={application}"),
        said(rf"wait: application={application} reason=killed value=0"),
    )


GUEST_MEASUREMENTS = replace(
    tests_image_scenario(
        "guest-measurements",
        MEASUREMENT_PROGRAM,
        tuple(
            line
            for case in MEASURED_CASES
            for line in (measured(case), *case_lines(MEASUREMENT, (case,)))
        ),
        Deadline.SOAK,
    ),
    arguments=INIT_OPTION + MEASUREMENT_PROGRAM + COLLECTOR_TRACE,
)

PROCESS_CHURN = replace(
    CYCLES, name="process-churn", arguments=(CYCLES.arguments or "") + COLLECTOR_TRACE
)

SYSTEM_MEASUREMENTS = replace(
    system_scenario(
        "system-measurements",
        (
            "mem",
            *("run boot/apps/spin.py",) * CPU_BOUND_TASKS,
            "run boot/apps/chatter.py tmp/chatter",
            "run boot/apps/chatter.py data/chatter",
            "run boot/apps/latency.py",
            f"wait {LATENCY_APPLICATION} 120",
            *(command for application in LOADED_APPLICATIONS for command in stopped(application)),
            *("run boot/apps/ballast.py",) * MEMORY_HOLDERS,
            f"wait {HOLDER_APPLICATIONS[0]} {SETTLE_SECONDS}",
            "mem",
            *(command for application in HOLDER_APPLICATIONS for command in stopped(application)),
            "shutdown",
        ),
        (
            ACCEPTED,
            RUNNING,
            MEMORY_REPORT,
            measured("ready-task-response"),
            exited(LATENCY_APPLICATION),
            *(line for application in LOADED_APPLICATIONS for line in reported_stop(application)),
            *(r"ballast: held=\d+",) * MEMORY_HOLDERS,
            completed("wait", "failed error=TIMED_OUT"),
            MEMORY_REPORT,
            *(line for application in HOLDER_APPLICATIONS for line in reported_stop(application)),
            STOPPED_CLEANLY,
        ),
        network=CLEAN_NETWORK,
        boot_overlay=(
            BootEntry("system/config", MEASUREMENT_CONFIGURATION),
            *(
                test_application(name)
                for name in ("spin.py", "chatter.py", "latency.py", "ballast.py")
            ),
        ),
    ),
    arguments=INIT_OPTION + MANAGER_PROGRAM + COLLECTOR_TRACE,
)
