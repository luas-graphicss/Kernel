from kernel_client import console
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import CANCELLED
from suites.support.expectations import error_code


def main() -> bool:
    return error_code(console.read_line, Startup().handles[0]) == CANCELLED
