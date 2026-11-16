from kernel_client import files
from kernel_client.processes import Startup
from kernel_protocol.services.files import (
    KIND_DIRECTORY,
    OPEN_CREATE,
    OPEN_DIRECTORY,
    OPEN_READ,
    OPEN_TRUNCATE,
    OPEN_WRITE,
)
from kernel_services.init.system import ServiceSystem
from suites.support.reporting import run_suite

REPLACE = OPEN_WRITE | OPEN_CREATE | OPEN_TRUNCATE
SEPARATOR = b"/"


def bind(run, services: ServiceSystem):
    def bound(context, checks) -> None:
        run(services, context, checks)

    return bound


def run_with_services(suite: str, cases) -> bool:
    startup = Startup()
    services = ServiceSystem(startup.handles[0], startup.identity)
    started = services.start()
    passed = run_suite(suite, [(name, bind(run, services)) for name, run in cases])
    return services.stop() and started and passed


def enter(services: ServiceSystem) -> files.Namespace:
    return files.Namespace(services.filesystem.endpoint, services.namespace)


def mount_report(namespace: files.Namespace, name: bytes):
    for report in namespace.status():
        if report.name == name:
            return report
    return None


def store(namespace: files.Namespace, path: bytes, data: bytes) -> None:
    opened = namespace.open(path, REPLACE)
    opened.write(0, data)
    opened.close()


def load(namespace: files.Namespace, path: bytes) -> bytes:
    opened = namespace.open(path, OPEN_READ)
    data = opened.read(0, opened.size)
    opened.close()
    return data


def names(namespace: files.Namespace, path: bytes) -> list[bytes]:
    opened = namespace.open(path, OPEN_DIRECTORY)
    listed = [name for name, _kind, _size in opened.entries()]
    opened.close()
    return listed


def sync(namespace: files.Namespace, path: bytes) -> None:
    opened = namespace.open(path, OPEN_DIRECTORY)
    opened.sync()
    opened.close()


def remove_tree(namespace: files.Namespace, path: bytes) -> None:
    for name in names(namespace, path):
        child = path + SEPARATOR + name
        if namespace.stat(child)[0] == KIND_DIRECTORY:
            remove_tree(namespace, child)
        else:
            namespace.remove(child)
    namespace.remove(path)
