from kernel_client import files
from kernel_client.processes import Startup
from kernel_protocol.services.files import OPEN_READ, OPEN_WRITE
from kernel_services.init.system import ServiceSystem
from suites.storage.digest import report_volume
from suites.support.platform import enter, store, sync

ROOT = b"data/journal"
LEDGER = ROOT + b"/ledger.bin"
ARCHIVE = ROOT + b"/archive"
FIRST_RECORDS = bytes(range(200)) * 30
MORE_RECORDS = bytes(range(100, 200)) * 50
REWRITTEN_OFFSET = 1000
SHORTENED_BYTES = 3000


def create_ledger(namespace: files.Namespace) -> None:
    namespace.make_directory(ROOT)
    store(namespace, LEDGER, FIRST_RECORDS)


def append_records(namespace: files.Namespace) -> None:
    ledger = namespace.open(LEDGER, OPEN_READ | OPEN_WRITE)
    ledger.write(len(FIRST_RECORDS), MORE_RECORDS)
    ledger.close()


def rewrite_records(namespace: files.Namespace) -> None:
    ledger = namespace.open(LEDGER, OPEN_WRITE)
    ledger.write(REWRITTEN_OFFSET, b"R" * 500)
    ledger.close()


def shorten_ledger(namespace: files.Namespace) -> None:
    ledger = namespace.open(LEDGER, OPEN_WRITE)
    ledger.truncate(SHORTENED_BYTES)
    ledger.close()


def archive_ledger(namespace: files.Namespace) -> None:
    namespace.make_directory(ARCHIVE)
    namespace.rename(LEDGER, ARCHIVE + b"/ledger.bin")


def replace_ledger(namespace: files.Namespace) -> None:
    store(namespace, LEDGER, b"a new ledger")
    namespace.rename(LEDGER, ARCHIVE + b"/ledger.bin")


def remove_archive(namespace: files.Namespace) -> None:
    namespace.remove(ARCHIVE + b"/ledger.bin")
    namespace.remove(ARCHIVE)


TRANSACTIONS = (
    create_ledger,
    append_records,
    rewrite_records,
    shorten_ledger,
    archive_ledger,
    replace_ledger,
    remove_archive,
)


def main() -> bool:
    startup = Startup()
    system = ServiceSystem(startup.handles[0], startup.identity)
    started = system.start()
    namespace = enter(system)
    for transaction in TRANSACTIONS:
        transaction(namespace)
        sync(namespace, b"data")
        report_volume(namespace)
    namespace.leave()
    return system.stop() and started
