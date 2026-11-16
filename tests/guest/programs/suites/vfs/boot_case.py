from kernel_client import files
from kernel_protocol.errors.codes import OK, READ_ONLY
from kernel_protocol.services.files import KIND_FILE, MODE_READ_ONLY, OPEN_WRITE
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.platform import enter, load, mount_report, names, store
from suites.support.reporting import Context

RELEASE = b"boot/system/release"
LICENSE = b"boot/system/license"
RELEASE_START = b"abi=1\nruntime=micropython-"
LICENSE_TITLE = b"GNU GENERAL PUBLIC LICENSE"
VERIFIED = b"verified"


def check_content(checks: Checks, namespace: files.Namespace) -> None:
    report = mount_report(namespace, b"boot")
    checks.require(
        report.code == OK and report.mode == MODE_READ_ONLY and report.reason == VERIFIED,
        "the boot image is mounted read-only after it was verified",
    )
    checks.require(
        names(namespace, b"") == [b"boot", b"data", b"tmp"],
        "the root of the namespace lists the mounts",
    )
    checks.require(
        names(namespace, b"boot") == [b"system"]
        and names(namespace, b"boot/system") == [b"license", b"release"],
        "the boot image lists the files of its manifest",
    )
    checks.require(
        load(namespace, RELEASE)[: len(RELEASE_START)] == RELEASE_START,
        "the release file names the interface and the runtime of the image",
    )
    kind, size = namespace.stat(LICENSE)
    text = load(namespace, LICENSE)
    checks.require(
        kind == KIND_FILE and len(text) == size and text.find(LICENSE_TITLE) >= 0,
        "a file of several blocks reads whole",
    )


def check_immutability(checks: Checks, namespace: files.Namespace) -> None:
    checks.require(
        error_code(namespace.open, RELEASE, OPEN_WRITE) == READ_ONLY
        and error_code(store, namespace, b"boot/new", b"x") == READ_ONLY
        and error_code(namespace.make_directory, b"boot/dir") == READ_ONLY
        and error_code(namespace.remove, RELEASE) == READ_ONLY
        and error_code(namespace.rename, RELEASE, b"boot/system/other") == READ_ONLY,
        "nothing in the boot image is created, changed or removed",
    )
    checks.require(
        error_code(namespace.remove, b"boot") == READ_ONLY
        and error_code(namespace.make_directory, b"other") == READ_ONLY
        and error_code(namespace.rename, b"tmp", b"scratch") == READ_ONLY
        and error_code(store, namespace, b"top.txt", b"x") == READ_ONLY,
        "mount points are not created, renamed or removed",
    )


def run(services: ServiceSystem, context: Context, checks: Checks) -> None:
    namespace = enter(services)
    check_content(checks, namespace)
    check_immutability(checks, namespace)
    namespace.leave()
