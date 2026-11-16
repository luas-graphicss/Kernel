from kernel_client import console, entropy, files
from kernel_protocol.errors.codes import OK, KernelError, error_name
from kernel_protocol.services.files import (
    MODE_READ_WRITE,
    OPEN_CREATE,
    OPEN_READ,
    OPEN_WRITE,
    MountReport,
)
from kernel_services.init.lifecycle import NO_ENDPOINT, Running
from kernel_services.init.manifest import BOOT_MOUNT, DATA_MOUNT
from kernel_services.init.system import NO_NAMESPACE, ServiceSystem

GREETING = b"console: service=ready\n"
CONSOLE_TIMEOUT_NANOSECONDS = 2000000000
ENTROPY_SAMPLE_BYTES = 32
RELEASE_PATH = b"boot/system/release"
RELEASE_BYTES = 4096
COUNTER_PATH = b"data/boots"
COUNTER_BYTES = 8
MODE_NAMES = ("read-only", "read-write")


def available(running: Running | None, name: str) -> bool:
    if running is None or running.endpoint == NO_ENDPOINT:
        print(f"init: {name}=unavailable")
        return False
    return True


def failed(name: str, error: KernelError) -> bool:
    print(f"init: {name}=failed error={error_name(error.code)}")
    return False


def check_console(running: Running | None) -> bool:
    if not available(running, "console") or running is None:
        return running is None
    try:
        console.write(running.endpoint, GREETING, CONSOLE_TIMEOUT_NANOSECONDS)
    except KernelError as error:
        return failed("console", error)
    print("init: console=ok")
    return True


def check_entropy(running: Running | None) -> bool:
    if not available(running, "entropy") or running is None:
        return running is None
    try:
        sample = entropy.read(running.endpoint, ENTROPY_SAMPLE_BYTES)
    except KernelError as error:
        return failed("entropy", error)
    varied = sample != bytes(ENTROPY_SAMPLE_BYTES)
    verdict = "ok" if varied else "failed"
    print(f"init: entropy={verdict} bytes={len(sample)}")
    return varied


def describe_mount(report: MountReport) -> None:
    name = str(report.name, "utf-8")
    if report.code != OK:
        print(f"init: mount={name} unavailable error={error_name(report.code)}")
        return
    reason = str(report.reason, "utf-8")
    print(f"init: mount={name} mode={MODE_NAMES[report.mode]} reason={reason}")


def read_release(namespace: files.Namespace) -> bool:
    release = namespace.open(RELEASE_PATH, OPEN_READ)
    content = release.read(0, RELEASE_BYTES)
    release.close()
    print(f"init: boot-file=system/release bytes={len(content)}")
    return len(content) != 0


def count_boot(namespace: files.Namespace) -> bool:
    counter = namespace.open(COUNTER_PATH, OPEN_READ | OPEN_WRITE | OPEN_CREATE)
    boots = int.from_bytes(counter.read(0, COUNTER_BYTES), "little") + 1
    written = counter.write(0, boots.to_bytes(COUNTER_BYTES, "little"))
    counter.sync()
    counter.close()
    print(f"init: data=ok boots={boots}")
    return written == COUNTER_BYTES


def check_mount(namespace: files.Namespace, report: MountReport) -> bool:
    describe_mount(report)
    if report.code != OK:
        return True
    try:
        if report.name == BOOT_MOUNT:
            return read_release(namespace)
        if report.name == DATA_MOUNT and report.mode == MODE_READ_WRITE:
            return count_boot(namespace)
    except KernelError as error:
        return failed(str(report.name, "utf-8"), error)
    return True


def check_filesystem(system: ServiceSystem) -> bool:
    running = system.filesystem
    if not available(running, "filesystem") or running is None or system.namespace == NO_NAMESPACE:
        return False
    succeeded = True
    try:
        namespace = files.Namespace(running.endpoint, system.namespace)
        for report in namespace.status():
            succeeded = check_mount(namespace, report) and succeeded
        namespace.leave()
    except KernelError as error:
        return failed("filesystem", error)
    return succeeded


def run(system: ServiceSystem) -> bool:
    succeeded = check_console(system.console)
    succeeded = check_entropy(system.entropy) and succeeded
    return check_filesystem(system) and succeeded
