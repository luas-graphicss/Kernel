from kernel_tool.scenarios.model import BootModule, Deadline, DeviceTreeSource, Image, Scenario
from kernel_tool.verification.transcript import KernelStatus

COLLECTOR_ROOTS = (*(f"s{index}" for index in range(12)), "stack-slot")
SELFTEST_CASES = ("integers", "bytes", "exceptions", "imports", "bindings", "collection")
USER_OUTPUT = (r"^init: ", r"^user: ")

BOOT = Scenario(
    name="boot",
    image=Image.KERNEL,
    boot_module=BootModule.INIT,
    expected_status=KernelStatus.OK,
    expected_lines=(
        r"^boot: hart=0 device-tree=0x[0-9a-f]{16} device-tree-bytes=\d+ device-tree-limit=65536$",
        r"^boot: region=boot-module base=0x[0-9a-f]{16} bytes=0x[0-9a-f]{16}$",
        r"^boot: console=ns16550a registers=0x[0-9a-f]{16}$",
        r"^policy: profile=ok memory-bytes=268435456 processes=16 ",
        r"^policy: admitted=init handle=\d+ memory-bytes=\d+ heap-bytes=\d+ stack-bytes=\d+$",
        r"^init: runtime=micropython privilege=user$",
        r"^init: allocated-bytes=\d+ checksum=(\d+) expected=\1$",
        r"^user: exit status=0$",
        r"^policy: reaped=init reason=exit value=0 live=0 memory-in-use=0$",
    ),
    forbidden_lines=(r"^trap: ", r"^panic: ", r"^Traceback "),
    repeats=3,
)

RUNTIME_SELFTEST = Scenario(
    name="runtime-selftest",
    image=Image.SELFTEST,
    boot_module=BootModule.NONE,
    expected_status=KernelStatus.OK,
    expected_lines=(
        *(
            rf"^selftest: probe=gc-roots root={root} rounds=\d+ result=ok$"
            for root in COLLECTOR_ROOTS
        ),
        *(rf"^selftest: case={case} checks=[1-9]\d* result=ok$" for case in SELFTEST_CASES),
        r"^selftest: probe=runtime-restart cycles=[1-9]\d* .* result=ok$",
    ),
    forbidden_lines=(r"^trap: ", r"^panic: ", r"^Traceback ", r"result=(?!ok$)"),
    deadline=Deadline.SELFTEST,
    compares_corpus=True,
)

DEVICE_TREE_TOO_LARGE = Scenario(
    name="device-tree-too-large",
    image=Image.KERNEL,
    boot_module=BootModule.INIT,
    expected_status=KernelStatus.FAILED,
    expected_lines=(r"^boot: rejected=device-tree reason=too-large$",),
    forbidden_lines=(r"^policy: ", *USER_OUTPUT),
    device_tree=DeviceTreeSource.OVERSIZED,
)

DEVICE_TREE_WITHOUT_MEMORY = Scenario(
    name="device-tree-without-memory",
    image=Image.KERNEL,
    boot_module=BootModule.INIT,
    expected_status=KernelStatus.FAILED,
    expected_lines=(r"^boot: rejected=device-tree reason=missing-memory$",),
    forbidden_lines=(r"^policy: ", *USER_OUTPUT),
    device_tree=DeviceTreeSource.WITHOUT_MEMORY,
)

INSUFFICIENT_MEMORY = Scenario(
    name="insufficient-memory",
    image=Image.KERNEL,
    boot_module=BootModule.INIT,
    expected_status=KernelStatus.FAILED,
    expected_lines=(
        r"^boot: rejected=memory reason=insufficient-ram "
        r"available=0x0000000008000000 required=0x0000000010000000$",
    ),
    forbidden_lines=(r"^policy: ", *USER_OUTPUT),
    memory_mib=128,
)

INCOMPATIBLE_SEGMENT = Scenario(
    name="incompatible-segment",
    image=Image.KERNEL,
    boot_module=BootModule.MISPLACED_SEGMENT,
    expected_status=KernelStatus.FAILED,
    expected_lines=(
        r"^policy: profile=ok ",
        r"^policy: rejected=boot-module reason=segment-outside-region$",
    ),
    forbidden_lines=USER_OUTPUT,
)

USER_FAULT = Scenario(
    name="user-fault",
    image=Image.KERNEL,
    boot_module=BootModule.FAULT,
    expected_status=KernelStatus.FAILED,
    expected_lines=(
        r"^policy: admitted=init ",
        r"^user: fault cause=illegal-instruction scause=0x0{15}2 sepc=0x[0-9a-f]{16} stval=",
        r"^policy: reaped=init reason=fault value=2 live=0 memory-in-use=0$",
    ),
    forbidden_lines=(r"^user: exit ", r"^trap: ", r"^panic: "),
)

SUPERVISOR_TRAP = Scenario(
    name="supervisor-trap",
    image=Image.SELFTEST,
    boot_module=BootModule.NONE,
    expected_status=KernelStatus.FAILED,
    expected_lines=(
        r"^trap: mode=supervisor cause=illegal-instruction scause=0x0{15}2 sepc=0x[0-9a-f]{16} ",
        r"^panic: reason=unexpected-supervisor-trap$",
    ),
    forbidden_lines=(r"^selftest: ",),
    arguments="probe=supervisor-trap",
)

BOOTSTRAP = (
    BOOT,
    RUNTIME_SELFTEST,
    DEVICE_TREE_TOO_LARGE,
    DEVICE_TREE_WITHOUT_MEMORY,
    INSUFFICIENT_MEMORY,
    INCOMPATIBLE_SEGMENT,
    USER_FAULT,
    SUPERVISOR_TRAP,
)
