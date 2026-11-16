from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import (
    INSTRUCTION_PAGE_FAULT,
    LOAD_PAGE_FAULT,
    STORE_PAGE_FAULT,
    faulted,
)
from suites.support.reporting import Context

INTRUDER = "suites.memory.intruder"
ATTEMPTS = (
    ("load", "null", LOAD_PAGE_FAULT),
    ("store", "null", STORE_PAGE_FAULT),
    ("jump", "null", INSTRUCTION_PAGE_FAULT),
    ("load", "supervisor-image", LOAD_PAGE_FAULT),
    ("store", "supervisor-image", STORE_PAGE_FAULT),
    ("jump", "supervisor-image", INSTRUCTION_PAGE_FAULT),
    ("load", "supervisor-memory", LOAD_PAGE_FAULT),
    ("store", "supervisor-memory", STORE_PAGE_FAULT),
    ("load", "console", LOAD_PAGE_FAULT),
    ("store", "console", STORE_PAGE_FAULT),
    ("load", "guard", LOAD_PAGE_FAULT),
    ("store", "guard", STORE_PAGE_FAULT),
    ("load", "above-stack", LOAD_PAGE_FAULT),
    ("load", "buffer-window", LOAD_PAGE_FAULT),
    ("store", "text", STORE_PAGE_FAULT),
    ("store", "read-only", STORE_PAGE_FAULT),
    ("jump", "heap", INSTRUCTION_PAGE_FAULT),
    ("jump", "stack", INSTRUCTION_PAGE_FAULT),
)


def run(context: Context, checks: Checks) -> None:
    for operation, target, cause in ATTEMPTS:
        outcome = children.run(context.system, INTRUDER, bytes(f"{operation} {target}", "ascii"))
        checks.require(outcome == faulted(cause), f"{operation} of {target} stops the process")
