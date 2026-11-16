from kernel_tool.scenarios.guest_program import (
    FORBIDDEN_LINES,
    case_lines,
    program_scenario,
    tests_image_scenario,
)
from kernel_tool.scenarios.model import BootModule, Deadline, Image, Scenario
from kernel_tool.verification.transcript import KernelStatus

CASES: dict[str, tuple[str, ...]] = {
    "memory": (
        "forbidden-access",
        "private-address-spaces",
        "system-call-pointers",
        "shared-buffers",
        "mapping-removed-while-blocked",
        "memory-cleared-between-processes",
        "quotas-and-reserve",
    ),
    "processes": (
        "exit-status-and-finalization",
        "spawn-authority-and-validation",
        "preemption-of-a-loop",
        "register-preservation",
        "process-capacity",
        "teardown-releases-resources",
    ),
    "capabilities": (
        "stale-and-forged-handles",
        "attenuated-delegation",
        "revocation-with-descendants",
        "capability-quota",
        "no-ambient-authority",
        "mappings-follow-capabilities",
    ),
    "ipc": (
        "malformed-messages",
        "delivery-and-transfer",
        "queue-limits",
        "peer-death",
        "cancellation",
        "deadlines",
        "reply-correlation",
        "endpoint-ownership",
        "deadlock-refusal",
    ),
    "scheduling": (
        "round-robin-among-equals",
        "priority-without-starvation",
        "priority-donation",
        "wait-chain-limit",
        "deadline-racing-a-reply",
        "clock-limits",
        "yield-to-an-equal",
    ),
}
CYCLES_CASE = "ten-thousand-process-and-ipc-cycles"
MEASURED_CYCLES = 10000


def cases_scenario(suite: str) -> Scenario:
    return tests_image_scenario("cases", f"suites.{suite}.main", case_lines(suite, CASES[suite]))


CYCLES = tests_image_scenario(
    "cycles",
    "suites.processes.cycles",
    (
        rf"^cycles: completed={MEASURED_CYCLES} frames-free=\d+$",
        *case_lines("processes", (CYCLES_CASE,)),
    ),
    Deadline.SOAK,
)

SPAWN_FAILURES = Scenario(
    name="spawn-failures",
    image=Image.SELFTEST,
    boot_module=BootModule.INIT,
    expected_status=KernelStatus.OK,
    expected_lines=(r"^selftest: probe=spawn-failure refusals=[1-9]\d* result=ok$",),
    forbidden_lines=(*FORBIDDEN_LINES, r"^selftest: .* result=(?!ok$)"),
    arguments="probe=spawn-failure",
)

SCHEDULE_TRACE = program_scenario(
    "schedule-trace",
    BootModule.INIT,
    "trace=schedule",
    (
        r"^sched: run=\d+ priority=1 result=spawn$",
        r"^sched: run=\d+ priority=1 result=blocked$",
        r"^sched: run=\d+ priority=2 result=\w+$",
        r"^sched: run=\d+ priority=2 result=exited$",
        r"^sched: run=\d+ priority=1 result=exited$",
    ),
)

GUEST_SUITES: dict[str, tuple[Scenario, ...]] = {
    "memory": (cases_scenario("memory"),),
    "processes": (cases_scenario("processes"), SPAWN_FAILURES, CYCLES),
    "capabilities": (cases_scenario("capabilities"),),
    "ipc": (cases_scenario("ipc"),),
    "scheduling": (cases_scenario("scheduling"), SCHEDULE_TRACE),
}
