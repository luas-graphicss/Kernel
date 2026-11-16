import _supervisor
from runtime_selftest.checks import Checks

LIMIT_COUNT = 7
REPEATED_CALLS = 20000
RETAINED_RESULTS = 8
MODULE_STATES = ("absent", "ok")


def rejects_arguments() -> bool:
    try:
        _supervisor.machine(1)
    except TypeError:
        return True
    return False


def run(checks: Checks) -> None:
    _hart, memory_base, memory_bytes = _supervisor.machine()
    limits = _supervisor.limits()
    region_base, region_bytes = _supervisor.user_region()

    checks.require(len(limits) == LIMIT_COUNT, "the profile exposes every compiled limit")
    checks.require(all(limit > 0 for limit in limits), "every compiled limit is positive")
    checks.require(memory_bytes >= limits[0], "the machine satisfies the memory of the profile")
    checks.require(
        memory_base <= region_base and region_base + region_bytes <= memory_base + memory_bytes,
        "the user region lies inside the machine memory",
    )
    checks.require(isinstance(_supervisor.arguments(), str), "boot arguments arrive as text")
    checks.require(rejects_arguments(), "bindings reject unexpected arguments")

    module = _supervisor.inspect_boot_module()
    checks.require(len(module) == 5 and module[0] in MODULE_STATES, "the boot module is described")

    reference = (_supervisor.machine(), _supervisor.limits(), _supervisor.user_region())
    retained = []
    for _ in range(REPEATED_CALLS):
        retained.append((_supervisor.machine(), _supervisor.limits(), _supervisor.user_region()))
        if len(retained) > RETAINED_RESULTS:
            retained.pop(0)
    checks.require(
        all(result == reference for result in retained),
        "results built by bindings stay valid under allocation pressure",
    )
