from kernel_client import files
from kernel_protocol.errors.codes import (
    ACCESS_DENIED,
    ALREADY_EXISTS,
    INVALID_ARGUMENT,
    IS_A_DIRECTORY,
    LIMIT_EXCEEDED,
    NOT_A_DIRECTORY,
    NOT_EMPTY,
    NOT_FOUND,
    UNSUPPORTED,
)
from kernel_protocol.services.files import (
    KIND_FILE,
    OPEN_CREATE,
    OPEN_DIRECTORY,
    OPEN_EXCLUSIVE,
    OPEN_READ,
    OPEN_TRUNCATE,
    OPEN_WRITE,
)
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.platform import enter, load, mount_report, names, remove_tree, store, sync
from suites.support.reporting import Context

ROOT = b"data/files"
FILE = ROOT + b"/a.bin"
DIRECTORY = ROOT + b"/dir"
INNER = DIRECTORY + b"/inner"
MOVED = DIRECTORY + b"/moved"
CROWDED = ROOT + b"/crowded"
PATTERN = bytes(range(256)) * 40
UPDATE_OFFSET = 5000
UPDATE = b"X" * 300
HOLE_END = 20000
SHORT_BYTES = 5
GROWN_BYTES = 9000
UNKNOWN_FLAG = 0x40
LONG_NAME_BYTES = 200
ENTRIES_THAT_FIT = 17
CREATE_NEW = OPEN_READ | OPEN_WRITE | OPEN_CREATE | OPEN_EXCLUSIVE


def check_creation(checks: Checks, namespace: files.Namespace) -> files.File:
    created = namespace.open(FILE, CREATE_NEW)
    checks.require(created.kind == KIND_FILE and created.size == 0, "a created file is empty")
    checks.require(
        error_code(namespace.open, FILE, CREATE_NEW) == ALREADY_EXISTS,
        "exclusive creation refuses a name that exists",
    )
    checks.require(
        created.write(0, b"") == 0 and created.read(0, 16) == b"",
        "zero bytes are written and read without effect",
    )
    checks.require(
        created.write(0, PATTERN) == len(PATTERN),
        "a write larger than one message is accepted whole",
    )
    checks.require(
        namespace.stat(FILE) == (KIND_FILE, len(PATTERN)),
        "the size follows the last byte written",
    )
    checks.require(created.read(0, len(PATTERN)) == PATTERN, "the file reads back what it holds")
    checks.require(
        created.read(len(PATTERN) - 10, 100) == PATTERN[-10:]
        and created.read(len(PATTERN), 8) == b"",
        "a read stops at the end of the file",
    )
    return created


def check_updates(checks: Checks, namespace: files.Namespace, opened: files.File) -> None:
    opened.write(UPDATE_OFFSET, UPDATE)
    updated = PATTERN[:UPDATE_OFFSET] + UPDATE + PATTERN[UPDATE_OFFSET + len(UPDATE) :]
    checks.require(
        opened.read(0, len(PATTERN)) == updated, "a write inside the file replaces only its range"
    )
    opened.write(HOLE_END, b"tail")
    hole = HOLE_END - len(PATTERN)
    checks.require(
        opened.read(len(PATTERN), hole) == bytes(hole) and opened.read(HOLE_END, 4) == b"tail",
        "a write past the end leaves a hole that reads as zeros",
    )
    opened.truncate(SHORT_BYTES)
    checks.require(
        namespace.stat(FILE) == (KIND_FILE, SHORT_BYTES)
        and opened.read(0, 100) == PATTERN[:SHORT_BYTES],
        "truncation drops everything after the new length",
    )
    opened.truncate(GROWN_BYTES)
    checks.require(
        opened.read(0, GROWN_BYTES) == PATTERN[:SHORT_BYTES] + bytes(GROWN_BYTES - SHORT_BYTES),
        "growing a file exposes zeros and never the bytes it dropped",
    )


def check_open_rules(checks: Checks, namespace: files.Namespace) -> None:
    reader = namespace.open(FILE, OPEN_READ)
    writer = namespace.open(FILE, OPEN_WRITE)
    checks.require(
        error_code(reader.write, 0, b"x") == ACCESS_DENIED
        and error_code(writer.read, 0, 1) == ACCESS_DENIED,
        "a handle does only what it was opened for",
    )
    reader.close()
    writer.close()
    checks.require(
        error_code(namespace.open, ROOT + b"/missing", OPEN_READ) == NOT_FOUND,
        "opening a missing file without the create flag fails",
    )
    checks.require(
        error_code(namespace.open, ROOT, OPEN_READ) == IS_A_DIRECTORY
        and error_code(namespace.open, ROOT, OPEN_DIRECTORY | OPEN_WRITE) == IS_A_DIRECTORY
        and error_code(namespace.open, FILE, OPEN_DIRECTORY) == NOT_A_DIRECTORY,
        "files and directories are opened each in their own way",
    )
    checks.require(
        error_code(namespace.open, FILE, 0) == INVALID_ARGUMENT
        and error_code(namespace.open, FILE, OPEN_READ | UNKNOWN_FLAG) == INVALID_ARGUMENT
        and error_code(namespace.open, FILE, OPEN_READ | OPEN_TRUNCATE) == INVALID_ARGUMENT,
        "open refuses no access, unknown flags and truncation without writing",
    )


def check_renames(checks: Checks, namespace: files.Namespace) -> None:
    store(namespace, ROOT + b"/one", b"1")
    store(namespace, ROOT + b"/two", b"22")
    namespace.make_directory(DIRECTORY)
    namespace.make_directory(INNER)
    namespace.rename(ROOT + b"/one", MOVED)
    checks.require(
        load(namespace, MOVED) == b"1" and error_code(namespace.stat, ROOT + b"/one") == NOT_FOUND,
        "a rename moves an entry between directories",
    )
    namespace.rename(ROOT + b"/two", MOVED)
    checks.require(load(namespace, MOVED) == b"22", "a rename replaces an existing file")
    checks.require(
        error_code(namespace.rename, DIRECTORY, INNER + b"/again") == INVALID_ARGUMENT,
        "a directory does not move into itself",
    )
    checks.require(
        error_code(namespace.rename, MOVED, INNER) == IS_A_DIRECTORY
        and error_code(namespace.rename, INNER, MOVED) == NOT_A_DIRECTORY,
        "a rename replaces only an entry of the same kind",
    )
    checks.require(
        error_code(namespace.rename, MOVED, b"tmp/moved") == UNSUPPORTED
        and error_code(namespace.rename, ROOT + b"/missing", ROOT + b"/other") == NOT_FOUND,
        "a rename does not cross mounts and needs its source",
    )
    checks.require(
        error_code(namespace.remove, DIRECTORY) == NOT_EMPTY,
        "a directory with entries is not removed",
    )


def check_directory_capacity(checks: Checks, namespace: files.Namespace) -> None:
    created = []
    namespace.make_directory(CROWDED)
    for index in range(ENTRIES_THAT_FIT):
        created.append(bytes(f"entry-{index:02d}-", "ascii") + b"n" * LONG_NAME_BYTES)
        store(namespace, CROWDED + b"/" + created[index], b"")
    checks.require(
        names(namespace, CROWDED) == sorted(created), "a directory lists its entries in order"
    )
    checks.require(
        error_code(store, namespace, CROWDED + b"/one-too-many-" + b"n" * LONG_NAME_BYTES, b"")
        == LIMIT_EXCEEDED,
        "a directory that is full refuses another entry",
    )


def run(services: ServiceSystem, context: Context, checks: Checks) -> None:
    namespace = enter(services)
    namespace.make_directory(ROOT)
    before = mount_report(namespace, b"data").generation
    opened = check_creation(checks, namespace)
    check_updates(checks, namespace, opened)
    check_open_rules(checks, namespace)
    opened.sync()
    opened.close()
    checks.require(
        mount_report(namespace, b"data").generation == before + 1,
        "a sync commits one generation of the volume",
    )
    check_renames(checks, namespace)
    check_directory_capacity(checks, namespace)
    remove_tree(namespace, ROOT)
    sync(namespace, b"data")
    namespace.leave()
