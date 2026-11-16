from kernel_client import files
from kernel_protocol.errors.codes import NO_SPACE, KernelError
from kernel_protocol.services.files import (
    MAX_TRANSFER_BYTES,
    OPEN_CREATE,
    OPEN_READ,
    OPEN_WRITE,
)
from kernel_services.init.system import ServiceSystem
from runtime_selftest.checks import Checks
from suites.support.expectations import error_code
from suites.support.platform import enter, mount_report, remove_tree, store, sync
from suites.support.reporting import Context

ROOT = b"data/capacity"
BIG = ROOT + b"/big.bin"
AGAIN = ROOT + b"/again.bin"
PATTERN = bytes(range(251))
PROBED_BYTES = 64
BLOCK_BYTES = 4096


def content_at(offset: int, length: int) -> bytes:
    start = offset % len(PATTERN)
    repeats = (start + length) // len(PATTERN) + 1
    return (PATTERN * repeats)[start : start + length]


class Filling:
    def __init__(self) -> None:
        self.accepted = 0
        self.short_writes = 0

    def run(self, opened: files.File, limit: int) -> None:
        while self.accepted < limit:
            try:
                written = opened.write(self.accepted, content_at(self.accepted, MAX_TRANSFER_BYTES))
            except KernelError as error:
                if error.code != NO_SPACE:
                    raise
                return
            self.accepted += written
            if written < MAX_TRANSFER_BYTES:
                self.short_writes += 1


def check_full_volume(checks: Checks, namespace: files.Namespace, total_bytes: int) -> int:
    big = namespace.open(BIG, OPEN_READ | OPEN_WRITE | OPEN_CREATE)
    filling = Filling()
    filling.run(big, total_bytes)
    accepted = filling.accepted
    next_block = (accepted + BLOCK_BYTES - 1) // BLOCK_BYTES * BLOCK_BYTES
    checks.require(
        0 < accepted < total_bytes and filling.short_writes > 0,
        "a write that does not fit whole is accepted in part until the blocks run out",
    )
    checks.require(
        error_code(big.write, next_block, b"x") == NO_SPACE,
        "a full volume refuses data that needs another block",
    )
    checks.require(
        big.read(accepted - PROBED_BYTES, PROBED_BYTES)
        == content_at(accepted - PROBED_BYTES, PROBED_BYTES)
        and big.read(0, PROBED_BYTES) == content_at(0, PROBED_BYTES),
        "the bytes accepted before the volume filled are intact",
    )
    big.sync()
    big.close()
    return accepted


def run(system: ServiceSystem, context: Context, checks: Checks) -> None:
    namespace = enter(system)
    namespace.make_directory(ROOT)
    total_blocks = mount_report(namespace, b"data").total_blocks
    accepted = check_full_volume(checks, namespace, total_blocks * BLOCK_BYTES)
    checks.require(
        mount_report(namespace, b"data").free_blocks < total_blocks // 4,
        "a full volume still commits what it holds",
    )
    namespace.remove(BIG)
    again = namespace.open(AGAIN, OPEN_READ | OPEN_WRITE | OPEN_CREATE)
    refilling = Filling()
    refilling.run(again, accepted // 2)
    checks.require(
        refilling.accepted >= accepted // 2,
        "the blocks of a removed file are used again once no committed root needs them",
    )
    again.close()
    store(namespace, ROOT + b"/small.txt", b"still writable")
    remove_tree(namespace, ROOT)
    sync(namespace, b"data")
    namespace.leave()
