from dataclasses import replace

from kernel_tool.scenarios.model import (
    SYSTEM_DEVICES,
    BootEntry,
    DataCheck,
    DataDisk,
    DataSource,
    Scenario,
)
from kernel_tool.scenarios.shell import completed, said, system_scenario
from kernel_tool.scenarios.system_suites import (
    ACCEPTED,
    CLEAN_NETWORK,
    RUNNING,
    STOPPED_CLEANLY,
    exited,
)

RELEASE_JOURNEY = "release-journey"
NEXT_VERSION = "next"
NEXT_RELEASE = "tests/guest/releases/next.release"
TEST_APPLICATIONS = "tests/guest/apps"
NOTE = "kept across releases"
ADDED = "written by the next release"
RELEASED_VERSION = r"version=\d+\.\d+\.\d+\S*"
SHELL_READY_SERVICE = r"^system: service=shell state=ready$"
KEPT_VOLUME = replace(SYSTEM_DEVICES, data=DataDisk(DataSource.KEPT))
DAMAGED_VOLUME = replace(
    SYSTEM_DEVICES,
    data=DataDisk(DataSource.DAMAGED_NEWEST_ROOT, check=DataCheck.UNCHANGED),
)
UNKNOWN_VOLUME = replace(
    SYSTEM_DEVICES,
    data=DataDisk(DataSource.UNKNOWN_VERSION, check=DataCheck.UNCHANGED),
)


def test_application(name: str) -> BootEntry:
    return BootEntry(f"apps/{name}", f"{TEST_APPLICATIONS}/{name}")


BOOT_TO_SHELL = system_scenario(
    "boot-to-shell",
    ("shutdown",),
    (ACCEPTED, SHELL_READY_SERVICE, RUNNING, STOPPED_CLEANLY),
    network=CLEAN_NETWORK,
)

FIRST_INITIALIZATION = system_scenario(
    "first-initialization",
    (
        "cat boot/system/release",
        "mkdir data/site",
        f"write data/site/note {NOTE}",
        "sync",
        "shutdown",
    ),
    (
        ACCEPTED,
        RUNNING,
        said(RELEASED_VERSION),
        completed("mkdir"),
        said(rf"write: bytes={len(NOTE) + 1}"),
        said(r"sync: volumes=2"),
        STOPPED_CLEANLY,
    ),
    network=CLEAN_NETWORK,
)

UPDATE_KEEPS_THE_VOLUME = system_scenario(
    "update-keeps-the-volume",
    (
        "cat boot/system/release",
        "cat data/site/note",
        "run boot/apps/counter.py",
        "wait 1 10",
        f"write data/site/added {ADDED}",
        "sync",
        "shutdown",
    ),
    (
        ACCEPTED,
        RUNNING,
        said(rf"version={NEXT_VERSION}"),
        said(NOTE),
        r"counter: runs=1 arguments=0$",
        exited(1),
        said(rf"write: bytes={len(ADDED) + 1}"),
        said(r"sync: volumes=2"),
        STOPPED_CLEANLY,
    ),
    devices=KEPT_VOLUME,
    network=CLEAN_NETWORK,
    boot_overlay=(BootEntry("system/release", NEXT_RELEASE), test_application("counter.py")),
)

ROLLBACK_KEEPS_THE_VOLUME = system_scenario(
    "rollback-keeps-the-volume",
    (
        "cat boot/system/release",
        "cat data/site/note",
        "cat data/site/added",
        "run boot/apps/counter.py",
        "wait 1 10",
        "shutdown",
    ),
    (
        ACCEPTED,
        RUNNING,
        said(RELEASED_VERSION),
        said(NOTE),
        said(ADDED),
        r"application: program=boot/apps/counter\.py error=NOT_FOUND$",
        exited(1, 1),
        STOPPED_CLEANLY,
    ),
    devices=KEPT_VOLUME,
    network=CLEAN_NETWORK,
)

DAMAGED_VOLUME_STAYS_READABLE = system_scenario(
    "damaged-volume-stays-readable",
    ("run boot/apps/sysinfo.py", "wait 1 10", "write data/refused content", "shutdown"),
    (
        ACCEPTED,
        r"sysinfo: mount=data mode=read-only$",
        exited(1),
        completed("write", "failed error=READ_ONLY"),
        STOPPED_CLEANLY,
    ),
    devices=DAMAGED_VOLUME,
    network=CLEAN_NETWORK,
)

UNKNOWN_FORMAT_IS_NOT_MOUNTED = system_scenario(
    "unknown-format-is-not-mounted",
    ("run boot/apps/sysinfo.py", "wait 1 10", "write data/refused content", "shutdown"),
    (
        ACCEPTED,
        r"sysinfo: mount=data state=unavailable$",
        exited(1),
        completed("write", r"failed error=\w+"),
        STOPPED_CLEANLY,
    ),
    devices=UNKNOWN_VOLUME,
    network=CLEAN_NETWORK,
)

RELEASE_SUITES: dict[str, tuple[Scenario, ...]] = {
    RELEASE_JOURNEY: (
        FIRST_INITIALIZATION,
        UPDATE_KEEPS_THE_VOLUME,
        ROLLBACK_KEEPS_THE_VOLUME,
        DAMAGED_VOLUME_STAYS_READABLE,
        UNKNOWN_FORMAT_IS_NOT_MOUNTED,
    ),
}
