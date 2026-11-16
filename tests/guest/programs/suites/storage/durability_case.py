from kernel_client import processes
from kernel_protocol.errors.codes import NOT_FOUND
from kernel_protocol.services.files import (
    MODE_READ_WRITE,
    OPEN_CREATE,
    OPEN_READ,
    OPEN_WRITE,
)
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.platform import enter, load, mount_report, remove_tree, store, sync
from suites.support.reporting import Context

ROOT = b"data/durable"
CONFIRMED = ROOT + b"/confirmed.bin"
UNCONFIRMED = ROOT + b"/unconfirmed.bin"
RENAMED = ROOT + b"/renamed.bin"
PATTERN = bytes(range(251)) * 37
LATE_BYTES = b"written after the sync"
CLEAN = b"clean"


def write_and_lose_the_service(system: ServiceSystem) -> int:
    namespace = enter(system)
    namespace.make_directory(ROOT)
    confirmed = namespace.open(CONFIRMED, OPEN_READ | OPEN_WRITE | OPEN_CREATE)
    confirmed.write(0, PATTERN)
    confirmed.sync()
    generation = mount_report(namespace, b"data").generation
    confirmed.write(0, LATE_BYTES)
    store(namespace, UNCONFIRMED, PATTERN)
    namespace.rename(CONFIRMED, RENAMED)
    processes.kill(system.filesystem.process)
    return generation


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    generation = write_and_lose_the_service(system)
    checks.require(system.restart_filesystem(), "the file service starts again after it was killed")
    namespace = enter(system)
    report = mount_report(namespace, b"data")
    checks.require(
        report.generation == generation
        and report.mode == MODE_READ_WRITE
        and report.reason == CLEAN,
        "the volume mounts at the generation whose sync was confirmed",
    )
    checks.require(
        load(namespace, CONFIRMED) == PATTERN,
        "a file whose sync was confirmed survives the loss of the service",
    )
    checks.require(
        error_code(namespace.stat, UNCONFIRMED) == NOT_FOUND
        and error_code(namespace.stat, RENAMED) == NOT_FOUND,
        "changes that were never synced are absent as a whole",
    )
    remove_tree(namespace, ROOT)
    sync(namespace, b"data")
    namespace.leave()
