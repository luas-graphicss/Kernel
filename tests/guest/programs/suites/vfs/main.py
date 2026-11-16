from suites.support.platform import run_with_services
from suites.vfs import (
    boot_case,
    clients_case,
    files_case,
    handles_case,
    namespaces_case,
    paths_case,
    restart_case,
)

CASES = (
    ("path-resolution", paths_case.run),
    ("files-and-directories", files_case.run),
    ("open-handles", handles_case.run),
    ("namespaces-and-rights", namespaces_case.run),
    ("boot-image", boot_case.run),
    ("concurrent-clients", clients_case.run),
    ("service-restart", restart_case.run),
)


def main() -> bool:
    return run_with_services("vfs", CASES)
