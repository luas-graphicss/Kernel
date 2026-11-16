from kernel_client import files
from kernel_protocol.errors.codes import INVALID_HANDLE, LIMIT_EXCEEDED, NOT_FOUND
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.files import OPEN_READ, OPEN_WRITE
from kernel_services.filesystem.namespace.table import MAX_FILES
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.platform import enter, load, remove_tree, store
from suites.support.reporting import Context

ROOT = b"data/handles"
FILE = ROOT + b"/open.bin"
CONTENT = bytes(range(200))
REPLACEMENT = b"written under the same name"
VISITOR = "suites.vfs.visitor"
NEVER_ISSUED_HANDLE = 0x7FFFFFFF


def check_removed_while_open(checks: Checks, namespace: files.Namespace) -> None:
    store(namespace, FILE, CONTENT)
    opened = namespace.open(FILE, OPEN_READ | OPEN_WRITE)
    namespace.remove(FILE)
    checks.require(
        error_code(namespace.stat, FILE) == NOT_FOUND, "a removed file leaves its directory at once"
    )
    checks.require(
        opened.read(0, len(CONTENT)) == CONTENT, "an open handle still reads a removed file"
    )
    checks.require(
        error_code(opened.write, 0, b"late") == NOT_FOUND, "a removed file accepts no more writes"
    )
    store(namespace, FILE, REPLACEMENT)
    checks.require(
        opened.read(0, len(CONTENT)) == CONTENT and load(namespace, FILE) == REPLACEMENT,
        "a new file under the same name is another file",
    )
    opened.close()
    checks.require(error_code(opened.read, 0, 1) == INVALID_HANDLE, "a closed handle is refused")
    checks.require(
        error_code(namespace.request, files.OPERATION_READ, NEVER_ISSUED_HANDLE, bytes(12))
        == INVALID_HANDLE,
        "a handle the service never issued is refused",
    )


def check_limit(checks: Checks, namespace: files.Namespace) -> None:
    opened = [namespace.open(FILE, OPEN_READ) for _handle in range(MAX_FILES)]
    checks.require(
        error_code(namespace.open, FILE, OPEN_READ) == LIMIT_EXCEEDED,
        "the handles open at one time are bounded",
    )
    for handle in opened:
        handle.close()
    namespace.open(FILE, OPEN_READ).close()


def check_ownership(
    checks: Checks, services: ServiceSystem, context: Context, namespace: files.Namespace
) -> None:
    opened = namespace.open(FILE, OPEN_READ)
    argument = bytes(f"stranger {namespace.instance} {namespace.session} {opened.handle}", "ascii")
    grants = ((services.filesystem.endpoint, RIGHT_SEND), (services.namespace, RIGHT_SEND))
    checks.require(
        children.run(context.system, VISITOR, argument, grants=grants) == EXITED_CLEANLY,
        "another process cannot use the session or the handles of this one",
    )
    other = enter(services)
    borrowed = other.open(FILE, OPEN_READ)
    other.leave()
    checks.require(
        error_code(borrowed.read, 0, 1) == INVALID_HANDLE,
        "leaving a session closes the handles it opened",
    )
    checks.require(opened.read(0, 4) == REPLACEMENT[:4], "the handles of other sessions stay open")
    opened.close()


def run(services: ServiceSystem, context: Context, checks: Checks) -> None:
    namespace = enter(services)
    namespace.make_directory(ROOT)
    check_removed_while_open(checks, namespace)
    check_limit(checks, namespace)
    check_ownership(checks, services, context, namespace)
    remove_tree(namespace, ROOT)
    namespace.leave()
