from kernel_client.processes import Startup
from kernel_services.init.system import ServiceSystem
from suites.storage.digest import report_volume
from suites.storage.tree import tree_is_intact, write_tree
from suites.support.platform import enter


def main() -> bool:
    startup = Startup()
    system = ServiceSystem(startup.handles[0], startup.identity)
    started = system.start()
    namespace = enter(system)
    write_tree(namespace)
    written = tree_is_intact(namespace)
    verdict = "ok" if written else "failed"
    print(f"storage: tree=written result={verdict}")
    report_volume(namespace)
    namespace.leave()
    return system.stop() and started and written
