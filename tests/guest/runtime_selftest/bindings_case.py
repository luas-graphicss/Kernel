import _supervisor
from runtime_selftest.checks import Checks

LIMIT_COUNT = 7
REPEATED_CALLS = 20000
RETAINED_RESULTS = 8
PROGRAM_STATES = ("absent", "ok")


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
    frame_bytes, usable_frames, free_frames, reserve_frames = _supervisor.memory()

    checks.require(len(limits) == LIMIT_COUNT, "the profile exposes every compiled limit")
    checks.require(all(limit > 0 for limit in limits), "every compiled limit is positive")
    checks.require(memory_bytes >= limits[0], "the machine satisfies the memory of the profile")
    checks.require(
        region_base + region_bytes <= memory_base or region_base >= memory_base + memory_bytes,
        "the user region does not alias the machine memory",
    )
    checks.require(
        reserve_frames < free_frames <= usable_frames
        and usable_frames * frame_bytes < memory_bytes,
        "the frame pool keeps a reserve inside the machine memory",
    )
    checks.require(isinstance(_supervisor.arguments(), str), "boot arguments arrive as text")
    checks.require(rejects_arguments(), "bindings reject unexpected arguments")
    checks.require(_supervisor.prepare_program() in PROGRAM_STATES, "the boot module is described")
    checks.require(len(_supervisor.counters()) > 0, "resource counters are exposed")

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
