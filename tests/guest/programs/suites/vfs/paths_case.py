from kernel_client import capabilities, files
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    LIMIT_EXCEEDED,
    NOT_A_DIRECTORY,
    NOT_FOUND,
)
from kernel_protocol.services.files import (
    KIND_DIRECTORY,
    KIND_FILE,
    MAX_PATH_COMPONENTS,
    NAMESPACE_ALL,
)
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.platform import enter, remove_tree, store
from suites.support.reporting import Context

ROOT = b"tmp/paths"
BRANCH = ROOT + b"/a"
NESTED = BRANCH + b"/b"
NOTE = NESTED + b"/note"
NOTE_TEXT = b"note"
LONGEST_NAME = b"n" * 255
UNICODE_NAME = b"a\xc3\xa7\xc3\xa3o-\xe2\x82\xac-\xf0\x9d\x84\x9e"
INVALID_NAMES = (
    b"\xff\xfe",
    b"\xc0\xaf",
    b"\xed\xa0\x80",
    b"\xe2\x82",
    b"\xf5\x80\x80\x80",
    b"nul\x00byte",
)
LONG_COMPONENT = b"/" + b"p" * 100
COMPONENTS_OVER_1024_BYTES = 11


def check_dots(checks: Checks, namespace: files.Namespace) -> None:
    checks.require(
        namespace.stat(NESTED + b"/../b/./note") == (KIND_FILE, len(NOTE_TEXT)),
        "dot and dot-dot resolve inside the namespace",
    )
    checks.require(
        namespace.stat(b"/tmp//paths/") == (KIND_DIRECTORY, 0),
        "empty components are skipped",
    )
    checks.require(
        namespace.stat(BRANCH + b"/../../..") == (KIND_DIRECTORY, 0),
        "a path may climb back to the root of its namespace",
    )
    checks.require(
        error_code(namespace.stat, b"..") == ACCESS_DENIED
        and error_code(namespace.stat, BRANCH + b"/../../../../tmp") == ACCESS_DENIED,
        "a path cannot climb above the root of its namespace",
    )


def check_names(checks: Checks, namespace: files.Namespace) -> None:
    namespace.make_directory(ROOT + b"/" + LONGEST_NAME)
    namespace.make_directory(ROOT + b"/" + UNICODE_NAME)
    checks.require(
        namespace.stat(ROOT + b"/" + LONGEST_NAME)[0] == KIND_DIRECTORY
        and namespace.stat(ROOT + b"/" + UNICODE_NAME)[0] == KIND_DIRECTORY,
        "a name of 255 bytes and a name of multi-byte UTF-8 are accepted",
    )
    checks.require(
        error_code(namespace.make_directory, ROOT + b"/" + LONGEST_NAME + b"n") == INVALID_ARGUMENT,
        "a name of 256 bytes is refused",
    )
    checks.require(
        all(
            error_code(namespace.make_directory, ROOT + b"/" + name) == INVALID_ARGUMENT
            for name in INVALID_NAMES
        ),
        "a name that is not UTF-8 or that holds a NUL is refused",
    )


def check_limits(checks: Checks, namespace: files.Namespace) -> None:
    too_many = ROOT + b"/x" * MAX_PATH_COMPONENTS
    too_long = ROOT + LONG_COMPONENT * COMPONENTS_OVER_1024_BYTES
    checks.require(
        error_code(namespace.stat, too_many) == LIMIT_EXCEEDED
        and error_code(namespace.stat, too_long) == LIMIT_EXCEEDED,
        "a path over 32 components or over 1024 bytes is refused",
    )
    checks.require(
        error_code(namespace.stat, ROOT + b"/missing") == NOT_FOUND
        and error_code(namespace.stat, NOTE + b"/below") == NOT_A_DIRECTORY,
        "a missing name and a file used as a directory have their own errors",
    )


def check_confinement(checks: Checks, services: ServiceSystem, namespace: files.Namespace) -> None:
    identity, capability = namespace.subspace(BRANCH, NAMESPACE_ALL)
    inner = files.Namespace(services.filesystem.endpoint, capability)
    checks.require(
        inner.stat(b"b/note") == (KIND_FILE, len(NOTE_TEXT)),
        "a subspace resolves paths from its own root",
    )
    checks.require(
        error_code(inner.stat, b"..") == ACCESS_DENIED
        and error_code(inner.stat, b"b/../../a/b/note") == ACCESS_DENIED
        and error_code(inner.stat, b"/tmp/paths") == NOT_FOUND,
        "a subspace cannot name anything above its root",
    )
    inner.leave()
    namespace.drop(identity)
    capabilities.close(capability)


def run(services: ServiceSystem, context: Context, checks: Checks) -> None:
    namespace = enter(services)
    for directory in (ROOT, BRANCH, NESTED):
        namespace.make_directory(directory)
    store(namespace, NOTE, NOTE_TEXT)
    check_dots(checks, namespace)
    check_names(checks, namespace)
    check_limits(checks, namespace)
    check_confinement(checks, services, namespace)
    remove_tree(namespace, ROOT)
    namespace.leave()
