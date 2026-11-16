from dataclasses import replace

from kernel_tool.scenarios.guest_program import (
    FORBIDDEN_LINES,
    case_lines,
    init_scenario,
    program_scenario,
    tests_image_scenario,
)
from kernel_tool.scenarios.model import (
    SYSTEM_DEVICES,
    BootModule,
    DataAttachment,
    DataCheck,
    DataDisk,
    DataSource,
    Deadline,
    Devices,
    Image,
    Scenario,
)
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
    "devices": (
        "discovery-and-claims",
        "feature-negotiation",
        "descriptor-validation",
        "block-requests",
        "entropy-source",
        "serial-port",
        "driver-exit-with-requests",
    ),
    "services": (
        "console-service",
        "entropy-service",
        "block-service",
        "service-authority",
    ),
    "vfs": (
        "path-resolution",
        "files-and-directories",
        "open-handles",
        "namespaces-and-rights",
        "boot-image",
        "concurrent-clients",
        "service-restart",
    ),
    "storage": (
        "durable-after-sync",
        "volume-full",
        "block-service-restart",
    ),
    "device-reset": (
        "request-deadline-and-reset",
        "memory-pinned-until-reset",
        "exit-with-a-request-in-flight",
        "device-reported-failure",
    ),
}
CYCLES_CASE = "ten-thousand-process-and-ipc-cycles"
MEASURED_CYCLES = 10000
VOLUME_REPORT = r"^storage: volume generation=\d+ digest=[0-9a-f]{8}$"
TYPED_LINES = "first line\rsecomd\x7f\x7fnd line\n"
SCRATCH_DEVICES = Devices(scratch=True, entropy=True)
UNTOUCHED = DataCheck.UNCHANGED


def cases_scenario(suite: str) -> Scenario:
    return tests_image_scenario("cases", f"suites.{suite}.main", case_lines(suite, CASES[suite]))


def with_data(source: DataSource, attachment: DataAttachment, check: DataCheck) -> Devices:
    return replace(SYSTEM_DEVICES, data=DataDisk(source, attachment, check))


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

DEVICE_CASES = replace(cases_scenario("devices"), devices=SCRATCH_DEVICES)

SERVICES = replace(
    tests_image_scenario(
        "services",
        "suites.services.main",
        (r"^console: written by a client$", *case_lines("services", CASES["services"])),
    ),
    devices=SCRATCH_DEVICES,
    serial_input=TYPED_LINES,
)

WITHOUT_ENTROPY = init_scenario(
    "without-entropy",
    replace(SYSTEM_DEVICES, entropy=False),
    (
        r"^init: devices serial=1 entropy=0 block=2$",
        r"^init: entropy=unavailable$",
        r"^init: mount=data mode=read-write reason=clean$",
    ),
)

PERSISTENCE_WRITE = replace(
    tests_image_scenario(
        "persistence-write",
        "suites.storage.writer",
        (r"^storage: tree=written result=ok$", VOLUME_REPORT),
    ),
    devices=with_data(DataSource.FORMATTED, DataAttachment.PLAIN, DataCheck.REPORTED),
)

PERSISTENCE_VERIFY = replace(
    tests_image_scenario(
        "persistence-verify",
        "suites.storage.reader",
        (r"^storage: tree=read result=ok$", VOLUME_REPORT),
    ),
    devices=with_data(DataSource.KEPT, DataAttachment.PLAIN, DataCheck.REPORTED),
)

READ_ONLY_DEVICE = init_scenario(
    "read-only-device",
    with_data(DataSource.KEPT, DataAttachment.READ_ONLY, UNTOUCHED),
    (r"^init: mount=data mode=read-only reason=device-read-only$",),
)

UNFORMATTED_DEVICE = init_scenario(
    "unformatted-device",
    with_data(DataSource.BLANK, DataAttachment.PLAIN, UNTOUCHED),
    (
        r"^filesystem: mount=data unavailable error=CORRUPTED$",
        r"^init: mount=data unavailable error=CORRUPTED$",
    ),
)

UNKNOWN_FORMAT_VERSION = init_scenario(
    "unknown-format-version",
    with_data(DataSource.UNKNOWN_VERSION, DataAttachment.PLAIN, UNTOUCHED),
    (r"^init: mount=data unavailable error=UNSUPPORTED$",),
)

DAMAGED_NEWEST_ROOT = init_scenario(
    "damaged-newest-root",
    with_data(DataSource.DAMAGED_NEWEST_ROOT, DataAttachment.PLAIN, UNTOUCHED),
    (r"^init: mount=data mode=read-only reason=newest-root-damaged$",),
)

FLUSH_FAILURE = init_scenario(
    "flush-failure",
    with_data(DataSource.FORMATTED, DataAttachment.FLUSH_FAILING, DataCheck.CONSISTENT),
    (
        r"^init: mount=data mode=read-write reason=clean$",
        r"^init: data=failed error=IO_ERROR$",
        r"^filesystem: stop=unsynced error=IO_ERROR$",
    ),
    KernelStatus.FAILED,
)

GUEST_SUITES: dict[str, tuple[Scenario, ...]] = {
    "memory": (cases_scenario("memory"),),
    "processes": (cases_scenario("processes"), SPAWN_FAILURES, CYCLES),
    "capabilities": (cases_scenario("capabilities"),),
    "ipc": (cases_scenario("ipc"),),
    "scheduling": (cases_scenario("scheduling"), SCHEDULE_TRACE),
    "devices": (DEVICE_CASES, SERVICES, WITHOUT_ENTROPY),
    "vfs": (replace(cases_scenario("vfs"), devices=SYSTEM_DEVICES),),
    "storage": (
        replace(cases_scenario("storage"), devices=SYSTEM_DEVICES),
        PERSISTENCE_WRITE,
        PERSISTENCE_VERIFY,
        READ_ONLY_DEVICE,
        UNFORMATTED_DEVICE,
        UNKNOWN_FORMAT_VERSION,
        DAMAGED_NEWEST_ROOT,
        FLUSH_FAILURE,
    ),
}
