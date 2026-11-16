from kernel_client import files
from kernel_protocol.services.files import KIND_DIRECTORY
from suites.support.platform import load, names, store, sync

ROOT = b"data/tree"
DIRECTORIES = (ROOT, ROOT + b"/reports", ROOT + b"/reports/2026", ROOT + b"/empty")
FILES = (
    (ROOT + b"/readme.txt", b"kept across a reboot\n"),
    (ROOT + b"/reports/2026/pattern.bin", bytes(range(256)) * 36),
    (ROOT + b"/reports/blank.bin", bytes(5000)),
    (ROOT + b"/reports/empty.bin", b""),
)
LISTINGS = (
    (ROOT, [b"empty", b"readme.txt", b"reports"]),
    (ROOT + b"/reports", [b"2026", b"blank.bin", b"empty.bin"]),
    (ROOT + b"/reports/2026", [b"pattern.bin"]),
    (ROOT + b"/empty", []),
)


def write_tree(namespace: files.Namespace) -> None:
    for directory in DIRECTORIES:
        namespace.make_directory(directory)
    for path, content in FILES:
        store(namespace, path, content)
    store(namespace, ROOT + b"/draft.txt", b"renamed before the sync")
    namespace.rename(ROOT + b"/draft.txt", ROOT + b"/readme.txt")
    store(namespace, ROOT + b"/readme.txt", FILES[0][1])
    sync(namespace, b"data")


def tree_is_intact(namespace: files.Namespace) -> bool:
    for path, content in FILES:
        if load(namespace, path) != content:
            return False
    for directory, listed in LISTINGS:
        if namespace.stat(directory)[0] != KIND_DIRECTORY or names(namespace, directory) != listed:
            return False
    return True
