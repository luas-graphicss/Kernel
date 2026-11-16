from kernel_client import capabilities, files, services
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    NOT_A_DIRECTORY,
    NOT_FOUND,
)
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.files import (
    NAMESPACE_DELEGATE,
    NAMESPACE_READ,
    NAMESPACE_WRITE,
    OPEN_WRITE,
    OPERATION_ENTER,
)
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.platform import enter, load, remove_tree, store
from suites.support.reporting import Context
from suites.vfs.visitor import INSIDE_NAME, INSIDE_NOTE

ROOT = b"tmp/spaces"
PUBLIC = ROOT + b"/public"
SECRET_FILE = ROOT + b"/secret.txt"
SECRET = b"outside the subspace"
SHOWN = b"inside the subspace"
UNKNOWN_RIGHT = 0x8
VISITOR = "suites.vfs.visitor"


def check_read_only(checks: Checks, endpoint: int, namespace: files.Namespace) -> None:
    identity, capability = namespace.subspace(PUBLIC, NAMESPACE_READ)
    reader = files.Namespace(endpoint, capability)
    checks.require(
        reader.rights == NAMESPACE_READ and load(reader, b"shown.txt") == SHOWN,
        "a subspace reads with the rights it was given",
    )
    checks.require(
        error_code(store, reader, b"new.txt", b"x") == ACCESS_DENIED
        and error_code(reader.open, b"shown.txt", OPEN_WRITE) == ACCESS_DENIED
        and error_code(reader.make_directory, b"dir") == ACCESS_DENIED
        and error_code(reader.rename, b"shown.txt", b"other.txt") == ACCESS_DENIED
        and error_code(reader.remove, b"shown.txt") == ACCESS_DENIED,
        "a read-only subspace changes nothing",
    )
    checks.require(
        error_code(reader.subspace, b"", NAMESPACE_READ) == ACCESS_DENIED,
        "a subspace without the delegate right creates no subspace",
    )
    reader.leave()
    namespace.drop(identity)
    capabilities.close(capability)


def check_delegation(checks: Checks, endpoint: int, namespace: files.Namespace) -> None:
    identity, capability = namespace.subspace(PUBLIC, NAMESPACE_READ | NAMESPACE_DELEGATE)
    middle = files.Namespace(endpoint, capability)
    checks.require(
        error_code(middle.subspace, b"", NAMESPACE_READ | NAMESPACE_WRITE) == ACCESS_DENIED,
        "a subspace holds no more rights than its origin",
    )
    checks.require(
        error_code(namespace.subspace, PUBLIC, 0) == INVALID_ARGUMENT
        and error_code(namespace.subspace, PUBLIC, UNKNOWN_RIGHT) == INVALID_ARGUMENT
        and error_code(namespace.subspace, PUBLIC + b"/shown.txt", NAMESPACE_READ)
        == NOT_A_DIRECTORY,
        "a subspace needs known rights and a directory as its root",
    )
    inner_identity, inner_capability = middle.subspace(b"", NAMESPACE_READ)
    inner = files.Namespace(endpoint, inner_capability)
    checks.require(
        error_code(namespace.drop, inner_identity) == NOT_FOUND,
        "only the session that created a subspace drops it",
    )
    namespace.drop(identity)
    checks.require(
        error_code(inner.stat, b"") == INVALID_HANDLE
        and error_code(middle.stat, b"") == INVALID_HANDLE,
        "dropping a namespace ends its sessions and the namespaces derived from it",
    )
    capabilities.close(inner_capability)
    capabilities.close(capability)


def check_confined_process(
    checks: Checks, endpoint: int, context: Context, namespace: files.Namespace
) -> None:
    identity, capability = namespace.subspace(PUBLIC, NAMESPACE_READ | NAMESPACE_WRITE)
    grants = ((endpoint, RIGHT_SEND), (capability, RIGHT_SEND))
    checks.require(
        children.run(context.system, VISITOR, b"confined", grants=grants) == EXITED_CLEANLY,
        "a process confined to a subspace works inside it and cannot leave it",
    )
    checks.require(
        load(namespace, PUBLIC + b"/" + INSIDE_NAME) == INSIDE_NOTE
        and load(namespace, SECRET_FILE) == SECRET,
        "the confined process wrote inside its subspace and nowhere else",
    )
    namespace.drop(identity)
    capabilities.close(capability)


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    endpoint = system.filesystem.endpoint
    namespace = enter(system)
    namespace.make_directory(ROOT)
    namespace.make_directory(PUBLIC)
    store(namespace, SECRET_FILE, SECRET)
    store(namespace, PUBLIC + b"/shown.txt", SHOWN)
    checks.require(
        error_code(services.call, endpoint, OPERATION_ENTER) == ACCESS_DENIED,
        "a session starts only after a namespace capability is presented",
    )
    check_read_only(checks, endpoint, namespace)
    check_delegation(checks, endpoint, namespace)
    check_confined_process(checks, endpoint, context, namespace)
    remove_tree(namespace, ROOT)
    namespace.leave()
