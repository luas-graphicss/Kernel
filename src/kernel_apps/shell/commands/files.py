from kernel_apps.shell.session import Session
from kernel_protocol.errors.codes import INVALID_ARGUMENT, OK, KernelError
from kernel_protocol.services.files import (
    KIND_DIRECTORY,
    MODE_READ_WRITE,
    OPEN_CREATE,
    OPEN_DIRECTORY,
    OPEN_READ,
    OPEN_TRUNCATE,
    OPEN_WRITE,
)

MAX_PRINTED_BYTES = 65536
READ_CHUNK_BYTES = 1024
ROOT = ""
LINE_BREAK = b"\n"
SEPARATOR = " "
KIND_NAMES = ("unknown", "file", "directory")
USAGE = "the command was not given its arguments"


def path_of(arguments: list[str]) -> bytes:
    if not arguments:
        raise KernelError(INVALID_ARGUMENT, USAGE)
    return bytes(arguments[0], "utf-8")


def list_directory(session: Session, arguments: list[str]) -> None:
    path = bytes(arguments[0] if arguments else ROOT, "utf-8")
    directory = session.files().open(path, OPEN_READ | OPEN_DIRECTORY)
    try:
        entries = directory.entries()
    finally:
        directory.close()
    for name, kind, size in entries:
        session.write(f"ls: name={str(name, 'utf-8')} kind={KIND_NAMES[kind]} size={size}")
    session.write(f"ls: entries={len(entries)}")


def print_file(session: Session, arguments: list[str]) -> None:
    opened = session.files().open(path_of(arguments), OPEN_READ)
    printed = 0
    ends_line = True
    try:
        if opened.kind == KIND_DIRECTORY or opened.size > MAX_PRINTED_BYTES:
            raise KernelError(INVALID_ARGUMENT, "cat prints files up to its limit")
        while printed < opened.size:
            chunk = opened.read(printed, READ_CHUNK_BYTES)
            if not chunk:
                break
            session.write_bytes(chunk)
            printed += len(chunk)
            ends_line = chunk.endswith(LINE_BREAK)
    finally:
        opened.close()
    if not ends_line:
        session.write_bytes(LINE_BREAK)
    session.write(f"cat: bytes={printed}")


def make_directory(session: Session, arguments: list[str]) -> None:
    session.files().make_directory(path_of(arguments))


def write_file(session: Session, arguments: list[str]) -> None:
    path = path_of(arguments)
    content = bytes(SEPARATOR.join(arguments[1:]), "utf-8") + LINE_BREAK
    opened = session.files().open(path, OPEN_WRITE | OPEN_CREATE | OPEN_TRUNCATE)
    try:
        written = opened.write(0, content)
    finally:
        opened.close()
    if written != len(content):
        raise KernelError(INVALID_ARGUMENT, "the file took less than the line")
    session.write(f"write: bytes={written}")


def remove(session: Session, arguments: list[str]) -> None:
    session.files().remove(path_of(arguments))


def sync(session: Session, arguments: list[str]) -> None:
    namespace = session.files()
    synced = 0
    for mount in namespace.status():
        if mount.code != OK or mount.mode != MODE_READ_WRITE:
            continue
        root = namespace.open(mount.name, OPEN_READ | OPEN_DIRECTORY)
        try:
            root.sync()
        finally:
            root.close()
        synced += 1
        session.write(f"sync: mount={str(mount.name, 'utf-8')} durable=1")
    session.write(f"sync: volumes={synced}")
