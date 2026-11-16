from kernel_client import capabilities, ipc, memory, processes
from kernel_protocol.errors.codes import LIMIT_EXCEEDED, OK, KernelError
from kernel_protocol.identity.rights import OBJECT_ENDPOINT, RIGHT_SEND
from runtime_selftest.checks import Checks
from suites.support.children import CHILD_HEAP_BYTES
from suites.support.expectations import error_code
from suites.support.layout import PAGE_BYTES
from suites.support.reporting import Context

SLEEPER = "suites.support.sleeper"
PROFILE_CAPABILITIES = 128
HELD_BY_THE_SUITE = 2
CREATION_ATTEMPTS = PROFILE_CAPABILITIES + 1


def create_until_refused() -> tuple[list[int], int]:
    endpoints = []
    for _ in range(CREATION_ATTEMPTS):
        try:
            endpoints.append(ipc.create_endpoint())
        except KernelError as error:
            return endpoints, error.code
    return endpoints, OK


def run(context: Context, checks: Checks) -> None:
    endpoints, refusal = create_until_refused()
    checks.require(
        len(endpoints) == PROFILE_CAPABILITIES - HELD_BY_THE_SUITE and refusal == LIMIT_EXCEEDED,
        "a process holds at most the capabilities of its quota",
    )
    full_table_refusals = (
        ("a derivation", error_code(capabilities.derive, endpoints[0], RIGHT_SEND)),
        ("a buffer", error_code(memory.create_buffer, PAGE_BYTES)),
        (
            "a spawn",
            error_code(
                processes.spawn,
                context.system,
                SLEEPER,
                b"",
                processes.DEFAULT_PRIORITY,
                CHILD_HEAP_BYTES,
                0,
                (),
            ),
        ),
    )
    for description, code in full_table_refusals:
        checks.require(code == LIMIT_EXCEEDED, f"{description} is refused while the table is full")
    for endpoint in endpoints:
        capabilities.close(endpoint)
    endpoint = ipc.create_endpoint()
    checks.require(
        capabilities.inspect(endpoint)[0] == OBJECT_ENDPOINT,
        "the table is usable again after it is emptied",
    )
    capabilities.close(endpoint)
