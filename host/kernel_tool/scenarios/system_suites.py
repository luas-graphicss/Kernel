import hashlib
import re
from dataclasses import replace

from kernel_tool.network.plan import (
    GREETING_LINES,
    GREETING_PORT,
    GREETING_WORDS_PER_LINE,
    PEER_ADDRESS,
    SILENT_PORT,
    NetworkPlan,
    greeting,
)
from kernel_tool.scenarios.guest_program import case_lines, tests_image_scenario
from kernel_tool.scenarios.model import (
    SYSTEM_DEVICES,
    BootEntry,
    DataDisk,
    DataSource,
    Network,
    Reported,
    Scenario,
)
from kernel_tool.scenarios.shell import (
    SYSTEM_FORBIDDEN,
    completed,
    refused_boot_scenario,
    said,
    system_scenario,
)

SUPERVISION = "supervision"
APPLICATIONS = "applications"
JOURNEY = "system-journey"
SUPERVISION_CASES = (
    "dependency-order",
    "readiness-and-degraded-state",
    "restart-with-a-pending-request",
    "restart-budget",
    "restart-window",
)
CONFIGURATION_PATH = "system/config"
CONFIGURATIONS = "tests/guest/configurations"
TEST_PROGRAMS = (
    "authority.py",
    "broken.txt",
    "counter.py",
    "failing.py",
    "hog.py",
    "idle.py",
    "spin.py",
)
TEST_PROGRAM_OVERLAY = tuple(
    BootEntry(f"apps/{name}", f"tests/guest/apps/{name}") for name in TEST_PROGRAMS
)
APPLICATION_LIMIT = 4
NOTE = "written before the restart"
NOTE_BYTES = len(NOTE) + 1
NOTE_WORDS = len(NOTE.split(" "))
GREETING_BYTES = len(greeting())
GREETING_WORDS = GREETING_LINES * GREETING_WORDS_PER_LINE
PEER = re.escape(PEER_ADDRESS)
ACCEPTED = r"^system: configuration=accepted name=kernel services=5$"
RUNNING = r"^system: state=running$"
STOPPED_CLEANLY = r"system: shutdown=complete clean=1$"
RESTART_REQUESTED = r"^kernel: power=restart$"
CLEAN_NETWORK = Network(NetworkPlan())


def exited(application: int, value: int = 0) -> str:
    return said(rf"wait: application={application} reason=exit value={value}")


def counted(path: str, lines: int, words: int, size: int) -> str:
    return rf"wordcount: path={path} lines={lines} words={words} bytes={size}$"


def rejected_configuration(name: str, source: str | None, reason: str, subject: str) -> Scenario:
    origin = None if source is None else f"{CONFIGURATIONS}/{source}"
    return refused_boot_scenario(
        f"configuration-{name}",
        (BootEntry(CONFIGURATION_PATH, origin),),
        (rf"^system: configuration=rejected reason={reason} subject={re.escape(subject)}$",),
    )


SUPERVISION_SCENARIO = tests_image_scenario(
    "supervision-cases",
    "suites.supervision.main",
    case_lines(SUPERVISION, SUPERVISION_CASES),
)

NETWORK_ABSENT = system_scenario(
    "network-absent",
    ("ps", "net", "ls boot", "shutdown"),
    (
        r"^system: devices serial=1 entropy=1 network=0 block=2$",
        ACCEPTED,
        r"^system: service=network state=restarting attempt=3 limit=3$",
        r"^system: service=network state=degraded restarts=3 window-seconds=60$",
        r"^system: service=shell state=ready$",
        r"^system: state=degraded$",
        said(r"ps: system=degraded"),
        said(r"ps: service=storage state=ready restarts=0/2 starts=1"),
        said(r"ps: service=network state=degraded restarts=3/3 starts=0"),
        completed("net", "failed error=BAD_STATE"),
        said(r"ls: entries=2"),
        STOPPED_CLEANLY,
    ),
)

REJECTED_CONFIGURATIONS = (
    rejected_configuration("missing", None, "missing-document", "boot/system/config"),
    rejected_configuration("circular", "circular.conf", "dependency-cycle", "console"),
    rejected_configuration(
        "excessive", "excessive.conf", "out-of-range", "service.network.heap_bytes"
    ),
    rejected_configuration(
        "inconsistent", "inconsistent.conf", "gateway-off-link", "interface.gateway"
    ),
)

APPLICATIONS_SCENARIO = system_scenario(
    "applications",
    (
        "run boot/apps/counter.py one two",
        "wait 1 10",
        "run boot/apps/counter.py",
        "wait 2 10",
        "run boot/apps/authority.py",
        "wait 3 10",
        "run boot/apps/failing.py",
        "wait 4 10",
        "run boot/apps/broken.txt",
        "wait 5 10",
        "run boot/apps/missing.py",
        "wait 6 10",
        "run boot/apps/spin.py",
        "wait 7 1",
        "ps",
        "kill 7",
        "wait 7 10",
        "run boot/apps/hog.py",
        "wait 8 30",
        *("run boot/apps/idle.py",) * (APPLICATION_LIMIT + 1),
        "wait 12 1",
        "ps",
        "kill 99",
        "shutdown",
    ),
    (
        ACCEPTED,
        RUNNING,
        r"counter: runs=1 arguments=2$",
        exited(1),
        r"counter: runs=1 arguments=0$",
        exited(2),
        r"authority: capabilities=[1-9]\d* send-only-endpoints=1 administration=refused "
        r"shell-modules=0 files=read-write network=granted$",
        exited(3),
        r"failing: about to raise$",
        r"ValueError: the program failed on purpose$",
        exited(4, 1),
        r"SyntaxError: invalid syntax$",
        exited(5, 1),
        r"application: program=boot/apps/missing\.py error=NOT_FOUND$",
        exited(6, 1),
        completed("wait", "failed error=TIMED_OUT"),
        said(r'ps: application=7 state=running command="boot/apps/spin\.py"'),
        said(r"kill: application=7"),
        said(r"wait: application=7 reason=killed value=0"),
        r"hog: started$",
        r"MemoryError: memory allocation failed",
        exited(8, 1),
        completed("run", "failed error=LIMIT_EXCEEDED"),
        completed("wait", "failed error=TIMED_OUT"),
        said(r'ps: application=12 state=running command="boot/apps/idle\.py"'),
        completed("kill", "failed error=NOT_FOUND"),
        r"system: shutdown=started action=shutdown$",
        rf"system: shutdown=applications stopped={APPLICATION_LIMIT}$",
        STOPPED_CLEANLY,
    ),
    network=CLEAN_NETWORK,
    boot_overlay=TEST_PROGRAM_OVERLAY,
)

FIRST_BOOT = system_scenario(
    "journey-first-boot",
    (
        "help",
        "ls",
        "cat boot/system/release",
        "mkdir data/journey",
        f"write data/journey/note {NOTE}",
        "cat data/journey/note",
        "run boot/apps/wordcount.py data/journey/note",
        "wait 1 10",
        "net",
        f"ping {PEER_ADDRESS} 2",
        "net neighbors",
        f"run boot/apps/fetch.py {PEER_ADDRESS} {GREETING_PORT} data/journey/greeting",
        "wait 2 20",
        "run boot/apps/wordcount.py data/journey/greeting",
        "wait 3 10",
        "run boot/apps/sysinfo.py",
        "wait 4 10",
        "write tmp/scratch volatile",
        "ls tmp",
        "rm tmp/scratch",
        "sync",
        "ps",
        "mem",
        "cat data/missing",
        "rm boot/system/release",
        f"run boot/apps/fetch.py {PEER_ADDRESS} {SILENT_PORT} data/journey/held",
        "wait 5 2",
        "shutdown restart",
    ),
    (
        ACCEPTED,
        RUNNING,
        said(r"help: shutdown \[restart\] - stop the system in order and power off or restart"),
        said(r"ls: name=data kind=directory size=0"),
        said(r"runtime=micropython-\d+\.\d+"),
        completed("mkdir"),
        said(rf"write: bytes={NOTE_BYTES}"),
        said(NOTE),
        counted("data/journey/note", 1, NOTE_WORDS, NOTE_BYTES),
        exited(1),
        said(
            r"net: address=10\.0\.2\.15/24 gateway=10\.0\.2\.2 mtu=1500 link=up "
            r"hardware=52:54:00:12:34:56"
        ),
        said(r"ping: sent=2 received=2"),
        said(r"net: neighbors=1"),
        rf"fetch: path=data/journey/greeting bytes={GREETING_BYTES}$",
        exited(2),
        counted("data/journey/greeting", GREETING_LINES, GREETING_WORDS, GREETING_BYTES),
        exited(3),
        r"sysinfo: mount=data mode=read-write$",
        r"sysinfo: address=10\.0\.2\.15/24 link=up$",
        exited(4),
        said(r"ls: name=scratch kind=file size=9"),
        completed("rm"),
        said(r"sync: mount=data durable=1"),
        said(r"sync: volumes=2"),
        said(r"ps: service=network state=ready restarts=0/3 starts=1"),
        said(r"mem: frames-usable=\d+ frames-free=\d+ frames-reserved=\d+ bytes-free=\d+"),
        completed("cat", "failed error=NOT_FOUND"),
        completed("rm", "failed error=READ_ONLY"),
        completed("wait", "failed error=TIMED_OUT"),
        r"system: shutdown=started action=restart$",
        r"system: shutdown=applications stopped=1$",
        STOPPED_CLEANLY,
    ),
    network=Network(
        NetworkPlan(),
        (
            Reported(
                "greeting",
                (("bytes", GREETING_BYTES), ("sha256", hashlib.sha256(greeting()).hexdigest())),
            ),
            Reported("held"),
        ),
    ),
    final_lines=(RESTART_REQUESTED,),
)

SECOND_BOOT = system_scenario(
    "journey-second-boot",
    (
        "cat data/journey/note",
        "run boot/apps/wordcount.py data/journey/greeting",
        "wait 1 10",
        "ls data/journey",
        "rm data/journey/note",
        "sync",
        "shutdown",
    ),
    (
        ACCEPTED,
        RUNNING,
        said(NOTE),
        counted("data/journey/greeting", GREETING_LINES, GREETING_WORDS, GREETING_BYTES),
        exited(1),
        said(rf"ls: name=greeting kind=file size={GREETING_BYTES}"),
        said(rf"ls: name=note kind=file size={NOTE_BYTES}"),
        completed("rm"),
        said(r"sync: volumes=2"),
        r"system: shutdown=started action=shutdown$",
        STOPPED_CLEANLY,
    ),
    devices=replace(SYSTEM_DEVICES, data=DataDisk(DataSource.KEPT)),
    network=CLEAN_NETWORK,
    forbidden_lines=(*SYSTEM_FORBIDDEN, r"^kernel: power="),
)

SYSTEM_SUITES: dict[str, tuple[Scenario, ...]] = {
    SUPERVISION: (SUPERVISION_SCENARIO, NETWORK_ABSENT, *REJECTED_CONFIGURATIONS),
    APPLICATIONS: (APPLICATIONS_SCENARIO,),
    JOURNEY: (FIRST_BOOT, SECOND_BOOT),
}
